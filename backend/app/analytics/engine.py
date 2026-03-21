from __future__ import annotations

"""
Analytics engine — club summaries, trends, dispersion, and handicap estimation.

All queries filter on is_filtered=True by default (bottom 20% already trimmed).
The engine operates on raw SQL queries for performance — no ORM overhead for
aggregation-heavy reads.
"""

import math
from dataclasses import dataclass, field
from datetime import date, timedelta
from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


# ═══════════════════════════════════════════════
# Data structures
# ═══════════════════════════════════════════════


@dataclass
class ClubSummary:
    """Per-club aggregate stats (filtered shots only)."""

    club_name: str
    shot_count: int
    session_count: int

    # Carry
    avg_carry: Decimal | None = None
    min_carry: Decimal | None = None
    max_carry: Decimal | None = None
    std_carry: Decimal | None = None

    # Ball speed
    avg_ball_speed: Decimal | None = None
    max_ball_speed: Decimal | None = None

    # Club speed (may be None if monitor doesn't measure)
    avg_club_speed: Decimal | None = None

    # Spin
    avg_spin_rate: int | None = None
    avg_launch_angle: Decimal | None = None

    # Dispersion
    avg_offline: Decimal | None = None
    std_offline: Decimal | None = None
    left_miss_pct: Decimal | None = None
    right_miss_pct: Decimal | None = None

    # Smash factor
    avg_smash: Decimal | None = None

    # Apex
    avg_apex: Decimal | None = None

    # Landing
    avg_landing_angle: Decimal | None = None


@dataclass
class SessionTrend:
    """One data point in a session-over-time trend."""

    session_date: date
    shot_count: int
    avg_carry: Decimal | None = None
    avg_ball_speed: Decimal | None = None
    avg_spin_rate: int | None = None
    avg_offline: Decimal | None = None
    avg_smash: Decimal | None = None
    avg_launch_angle: Decimal | None = None


@dataclass
class TrendSummary:
    """Are you improving? Compares recent vs earlier sessions."""

    metric: str
    current: Decimal | None = None
    previous: Decimal | None = None
    delta: Decimal | None = None
    direction: str = "flat"  # "up", "down", "flat"


@dataclass
class HandicapEstimate:
    """Estimated handicap range based on shot data patterns."""

    estimated_low: Decimal
    estimated_high: Decimal
    confidence: str  # "low", "medium", "high"
    factors: list[str] = field(default_factory=list)
    total_shots: int = 0
    unique_clubs: int = 0


@dataclass
class FullAnalytics:
    """Complete analytics response for a profile."""

    club_summaries: list[ClubSummary]
    session_trends: list[SessionTrend]
    improvement_summary: list[TrendSummary]
    handicap_estimate: HandicapEstimate | None = None


# ═══════════════════════════════════════════════
# Club ordering (for consistent display)
# ═══════════════════════════════════════════════

CLUB_ORDER = {
    "Driver": 1,
    "3 Wood": 2, "5 Wood": 3, "7 Wood": 4,
    "2 Hybrid": 5, "3 Hybrid": 6, "4 Hybrid": 7, "5 Hybrid": 8,
    "2 Iron": 9, "3 Iron": 10, "4 Iron": 11, "5 Iron": 12,
    "6 Iron": 13, "7 Iron": 14, "8 Iron": 15, "9 Iron": 16,
    "PW": 17, "GW": 18, "SW": 19, "LW": 20,
    "Putter": 21,
}


def _club_sort_key(name: str) -> int:
    return CLUB_ORDER.get(name, 50)


# ═══════════════════════════════════════════════
# Core analytics queries
# ═══════════════════════════════════════════════


async def get_club_summaries(
    db: AsyncSession,
    profile_id: str,
    *,
    date_from: date | None = None,
    date_to: date | None = None,
    club_name: str | None = None,
    ball_type: str | None = None,
    filtered_only: bool = True,
) -> list[ClubSummary]:
    """Get per-club aggregate statistics."""

    where_clauses = ["s.profile_id = :profile_id"]
    params: dict = {"profile_id": profile_id}

    if filtered_only:
        where_clauses.append("s.is_filtered = true")
    if date_from:
        where_clauses.append("s.shot_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("s.shot_date <= :date_to")
        params["date_to"] = date_to
    if club_name:
        where_clauses.append("s.club_name = :club_name")
        params["club_name"] = club_name
    if ball_type:
        where_clauses.append("s.ball_type = :ball_type")
        params["ball_type"] = ball_type

    where = " AND ".join(where_clauses)

    query = text(f"""
        SELECT
            s.club_name,
            COUNT(*) as shot_count,
            COUNT(DISTINCT s.shot_date) as session_count,
            ROUND(AVG(s.carry_yards)::numeric, 1) as avg_carry,
            ROUND(MIN(s.carry_yards)::numeric, 1) as min_carry,
            ROUND(MAX(s.carry_yards)::numeric, 1) as max_carry,
            ROUND(STDDEV_POP(s.carry_yards)::numeric, 1) as std_carry,
            ROUND(AVG(s.ball_speed_mph)::numeric, 1) as avg_ball_speed,
            ROUND(MAX(s.ball_speed_mph)::numeric, 1) as max_ball_speed,
            ROUND(AVG(s.club_speed_mph)::numeric, 1) as avg_club_speed,
            ROUND(AVG(s.spin_rate_rpm)::numeric, 0) as avg_spin_rate,
            ROUND(AVG(s.launch_angle_deg)::numeric, 1) as avg_launch_angle,
            ROUND(AVG(s.offline_yards)::numeric, 1) as avg_offline,
            ROUND(STDDEV_POP(s.offline_yards)::numeric, 1) as std_offline,
            ROUND(
                100.0 * COUNT(CASE WHEN s.offline_yards < 0 THEN 1 END)::numeric
                / NULLIF(COUNT(s.offline_yards), 0), 1
            ) as left_miss_pct,
            ROUND(
                100.0 * COUNT(CASE WHEN s.offline_yards > 0 THEN 1 END)::numeric
                / NULLIF(COUNT(s.offline_yards), 0), 1
            ) as right_miss_pct,
            ROUND(AVG(s.smash_factor)::numeric, 2) as avg_smash,
            ROUND(AVG(s.apex_feet)::numeric, 1) as avg_apex,
            ROUND(AVG(s.landing_angle_deg)::numeric, 1) as avg_landing_angle
        FROM shots s
        WHERE {where}
        GROUP BY s.club_name
        ORDER BY s.club_name
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    summaries = []
    for row in rows:
        summaries.append(ClubSummary(
            club_name=row.club_name,
            shot_count=row.shot_count,
            session_count=row.session_count,
            avg_carry=row.avg_carry,
            min_carry=row.min_carry,
            max_carry=row.max_carry,
            std_carry=row.std_carry,
            avg_ball_speed=row.avg_ball_speed,
            max_ball_speed=row.max_ball_speed,
            avg_club_speed=row.avg_club_speed,
            avg_spin_rate=int(row.avg_spin_rate) if row.avg_spin_rate else None,
            avg_launch_angle=row.avg_launch_angle,
            avg_offline=row.avg_offline,
            std_offline=row.std_offline,
            left_miss_pct=row.left_miss_pct,
            right_miss_pct=row.right_miss_pct,
            avg_smash=row.avg_smash,
            avg_apex=row.avg_apex,
            avg_landing_angle=row.avg_landing_angle,
        ))

    summaries.sort(key=lambda s: _club_sort_key(s.club_name))
    return summaries


async def get_session_trends(
    db: AsyncSession,
    profile_id: str,
    *,
    club_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    ball_type: str | None = None,
    filtered_only: bool = True,
) -> list[SessionTrend]:
    """Get per-session trends over time (for charting improvement)."""

    where_clauses = ["s.profile_id = :profile_id"]
    params: dict = {"profile_id": profile_id}

    if filtered_only:
        where_clauses.append("s.is_filtered = true")
    if club_name:
        where_clauses.append("s.club_name = :club_name")
        params["club_name"] = club_name
    if date_from:
        where_clauses.append("s.shot_date >= :date_from")
        params["date_from"] = date_from
    if date_to:
        where_clauses.append("s.shot_date <= :date_to")
        params["date_to"] = date_to
    if ball_type:
        where_clauses.append("s.ball_type = :ball_type")
        params["ball_type"] = ball_type

    where = " AND ".join(where_clauses)

    query = text(f"""
        SELECT
            s.shot_date,
            COUNT(*) as shot_count,
            ROUND(AVG(s.carry_yards)::numeric, 1) as avg_carry,
            ROUND(AVG(s.ball_speed_mph)::numeric, 1) as avg_ball_speed,
            ROUND(AVG(s.spin_rate_rpm)::numeric, 0) as avg_spin_rate,
            ROUND(AVG(s.offline_yards)::numeric, 1) as avg_offline,
            ROUND(AVG(s.smash_factor)::numeric, 2) as avg_smash,
            ROUND(AVG(s.launch_angle_deg)::numeric, 1) as avg_launch_angle
        FROM shots s
        WHERE {where}
        GROUP BY s.shot_date
        ORDER BY s.shot_date
    """)

    result = await db.execute(query, params)
    rows = result.fetchall()

    return [
        SessionTrend(
            session_date=row.shot_date,
            shot_count=row.shot_count,
            avg_carry=row.avg_carry,
            avg_ball_speed=row.avg_ball_speed,
            avg_spin_rate=int(row.avg_spin_rate) if row.avg_spin_rate else None,
            avg_offline=row.avg_offline,
            avg_smash=row.avg_smash,
            avg_launch_angle=row.avg_launch_angle,
        )
        for row in rows
    ]


async def get_improvement_summary(
    db: AsyncSession,
    profile_id: str,
    *,
    club_name: str | None = None,
    lookback_days: int = 30,
    filtered_only: bool = True,
) -> list[TrendSummary]:
    """
    Compare recent sessions vs earlier sessions.

    Splits the last N days in half — compares the more-recent half to the
    older half for each key metric.
    """

    midpoint = date.today() - timedelta(days=lookback_days // 2)
    start = date.today() - timedelta(days=lookback_days)

    where_base = ["s.profile_id = :profile_id", "s.shot_date >= :start"]
    params: dict = {"profile_id": profile_id, "start": start, "midpoint": midpoint}

    if filtered_only:
        where_base.append("s.is_filtered = true")
    if club_name:
        where_base.append("s.club_name = :club_name")
        params["club_name"] = club_name

    where = " AND ".join(where_base)

    query = text(f"""
        SELECT
            CASE WHEN s.shot_date >= :midpoint THEN 'recent' ELSE 'earlier' END as period,
            ROUND(AVG(s.carry_yards)::numeric, 1) as avg_carry,
            ROUND(AVG(s.ball_speed_mph)::numeric, 1) as avg_ball_speed,
            ROUND(AVG(s.spin_rate_rpm)::numeric, 0) as avg_spin_rate,
            ROUND(STDDEV_POP(s.offline_yards)::numeric, 1) as dispersion,
            ROUND(AVG(s.smash_factor)::numeric, 2) as avg_smash,
            ROUND(AVG(s.launch_angle_deg)::numeric, 1) as avg_launch_angle
        FROM shots s
        WHERE {where}
        GROUP BY period
    """)

    result = await db.execute(query, params)
    rows = {row.period: row for row in result.fetchall()}

    if not rows:
        return []

    recent = rows.get("recent")
    earlier = rows.get("earlier")

    metrics = [
        ("Carry Distance", "avg_carry", "up"),
        ("Ball Speed", "avg_ball_speed", "up"),
        ("Spin Rate", "avg_spin_rate", "neutral"),  # lower isn't always better
        ("Dispersion", "dispersion", "down"),  # lower = tighter = better
        ("Smash Factor", "avg_smash", "up"),
        ("Launch Angle", "avg_launch_angle", "neutral"),
    ]

    summaries = []
    for label, attr, better_dir in metrics:
        cur = getattr(recent, attr, None) if recent else None
        prev = getattr(earlier, attr, None) if earlier else None

        if cur is not None:
            cur = Decimal(str(cur))
        if prev is not None:
            prev = Decimal(str(prev))

        delta = None
        direction = "flat"
        if cur is not None and prev is not None:
            delta = cur - prev
            if abs(delta) < Decimal("0.1"):
                direction = "flat"
            elif better_dir == "up":
                direction = "up" if delta > 0 else "down"
            elif better_dir == "down":
                direction = "up" if delta < 0 else "down"  # improving when decreasing
            else:
                direction = "up" if delta > 0 else "down"

        summaries.append(TrendSummary(
            metric=label,
            current=cur,
            previous=prev,
            delta=delta,
            direction=direction,
        ))

    return summaries


# ═══════════════════════════════════════════════
# Handicap estimation
# ═══════════════════════════════════════════════

# Reference carry distances by handicap tier (7 Iron benchmark)
# Based on PGA/USGA distance studies and Trackman averages
_HANDICAP_7I_CARRY = [
    (Decimal("175"), Decimal("0"), Decimal("5")),    # scratch to 5
    (Decimal("165"), Decimal("5"), Decimal("10")),
    (Decimal("155"), Decimal("10"), Decimal("15")),
    (Decimal("145"), Decimal("15"), Decimal("20")),
    (Decimal("135"), Decimal("20"), Decimal("25")),
    (Decimal("120"), Decimal("25"), Decimal("30")),
    (Decimal("100"), Decimal("30"), Decimal("36")),
]

# Driver carry benchmarks
_HANDICAP_DRIVER_CARRY = [
    (Decimal("270"), Decimal("0"), Decimal("5")),
    (Decimal("250"), Decimal("5"), Decimal("10")),
    (Decimal("230"), Decimal("10"), Decimal("15")),
    (Decimal("210"), Decimal("15"), Decimal("20")),
    (Decimal("190"), Decimal("20"), Decimal("25")),
    (Decimal("170"), Decimal("25"), Decimal("30")),
    (Decimal("150"), Decimal("30"), Decimal("36")),
]

# Dispersion benchmarks (std dev of offline in yards, 7 Iron)
_HANDICAP_7I_DISPERSION = [
    (Decimal("5"), Decimal("0"), Decimal("5")),
    (Decimal("8"), Decimal("5"), Decimal("10")),
    (Decimal("12"), Decimal("10"), Decimal("15")),
    (Decimal("18"), Decimal("15"), Decimal("20")),
    (Decimal("25"), Decimal("20"), Decimal("25")),
    (Decimal("35"), Decimal("25"), Decimal("30")),
]


async def estimate_handicap(
    db: AsyncSession,
    profile_id: str,
    *,
    filtered_only: bool = True,
) -> HandicapEstimate | None:
    """
    Estimate handicap potential from shot data patterns.

    Uses multiple signals:
      1. 7 Iron carry distance (strongest signal)
      2. Driver carry distance
      3. 7 Iron dispersion (consistency)
      4. Smash factor (strike quality)
      5. Number of clubs hit (bag coverage)

    Returns an estimated range, not a single number. This is a
    practice-based estimate — actual handicap depends heavily on
    short game, putting, and course management which we can't measure.
    """

    where_clauses = ["s.profile_id = :profile_id"]
    params: dict = {"profile_id": profile_id}
    if filtered_only:
        where_clauses.append("s.is_filtered = true")
    where = " AND ".join(where_clauses)

    # Get per-club stats
    query = text(f"""
        SELECT
            s.club_name,
            COUNT(*) as shots,
            ROUND(AVG(s.carry_yards)::numeric, 1) as avg_carry,
            ROUND(STDDEV_POP(s.offline_yards)::numeric, 1) as std_offline,
            ROUND(AVG(s.smash_factor)::numeric, 2) as avg_smash,
            ROUND(AVG(s.ball_speed_mph)::numeric, 1) as avg_ball_speed
        FROM shots s
        WHERE {where}
        GROUP BY s.club_name
    """)

    result = await db.execute(query, params)
    rows = {row.club_name: row for row in result.fetchall()}

    if not rows:
        return None

    total_shots = sum(r.shots for r in rows.values())
    unique_clubs = len(rows)

    if total_shots < 20:
        return HandicapEstimate(
            estimated_low=Decimal("15"),
            estimated_high=Decimal("36"),
            confidence="low",
            factors=["Insufficient data — need at least 20 filtered shots"],
            total_shots=total_shots,
            unique_clubs=unique_clubs,
        )

    estimates: list[tuple[Decimal, Decimal, str]] = []  # (low, high, reason)

    # Signal 1: 7 Iron carry
    iron7 = rows.get("7 Iron")
    if iron7 and iron7.avg_carry and iron7.shots >= 10:
        carry = Decimal(str(iron7.avg_carry))
        for threshold, hc_low, hc_high in _HANDICAP_7I_CARRY:
            if carry >= threshold:
                estimates.append((hc_low, hc_high, f"7 Iron carry {carry} yds"))
                break
        else:
            estimates.append((Decimal("30"), Decimal("36"), f"7 Iron carry {carry} yds (below benchmarks)"))

    # Signal 2: Driver carry
    driver = rows.get("Driver")
    if driver and driver.avg_carry and driver.shots >= 5:
        carry = Decimal(str(driver.avg_carry))
        for threshold, hc_low, hc_high in _HANDICAP_DRIVER_CARRY:
            if carry >= threshold:
                estimates.append((hc_low, hc_high, f"Driver carry {carry} yds"))
                break

    # Signal 3: 7 Iron dispersion
    if iron7 and iron7.std_offline and iron7.shots >= 15:
        disp = Decimal(str(iron7.std_offline))
        for threshold, hc_low, hc_high in _HANDICAP_7I_DISPERSION:
            if disp <= threshold:
                estimates.append((hc_low, hc_high, f"7 Iron dispersion {disp} yds std dev"))
                break

    # Signal 4: Smash factor quality (across all clubs)
    all_smash = [Decimal(str(r.avg_smash)) for r in rows.values() if r.avg_smash]
    if all_smash:
        avg_smash = sum(all_smash) / len(all_smash)
        if avg_smash >= Decimal("1.45"):
            estimates.append((Decimal("0"), Decimal("10"), f"Avg smash factor {avg_smash:.2f} (excellent)"))
        elif avg_smash >= Decimal("1.40"):
            estimates.append((Decimal("5"), Decimal("15"), f"Avg smash factor {avg_smash:.2f} (good)"))
        elif avg_smash >= Decimal("1.35"):
            estimates.append((Decimal("10"), Decimal("20"), f"Avg smash factor {avg_smash:.2f} (average)"))
        else:
            estimates.append((Decimal("15"), Decimal("30"), f"Avg smash factor {avg_smash:.2f} (below average)"))

    # Signal 5: Bag coverage
    if unique_clubs >= 10:
        estimates.append((Decimal("0"), Decimal("15"), f"Full bag ({unique_clubs} clubs)"))
    elif unique_clubs >= 6:
        estimates.append((Decimal("5"), Decimal("20"), f"Good bag coverage ({unique_clubs} clubs)"))

    if not estimates:
        return HandicapEstimate(
            estimated_low=Decimal("15"),
            estimated_high=Decimal("30"),
            confidence="low",
            factors=["Need 7 Iron and Driver data for better estimate"],
            total_shots=total_shots,
            unique_clubs=unique_clubs,
        )

    # Aggregate: weighted average of estimates
    avg_low = sum(e[0] for e in estimates) / len(estimates)
    avg_high = sum(e[1] for e in estimates) / len(estimates)
    factors = [e[2] for e in estimates]

    # Confidence based on data volume and signal count
    confidence = "high" if len(estimates) >= 4 and total_shots >= 100 else (
        "medium" if len(estimates) >= 2 and total_shots >= 50 else "low"
    )

    return HandicapEstimate(
        estimated_low=Decimal(str(round(avg_low, 1))),
        estimated_high=Decimal(str(round(avg_high, 1))),
        confidence=confidence,
        factors=factors,
        total_shots=total_shots,
        unique_clubs=unique_clubs,
    )


# ═══════════════════════════════════════════════
# Full analytics bundle
# ═══════════════════════════════════════════════


async def get_full_analytics(
    db: AsyncSession,
    profile_id: str,
    *,
    club_name: str | None = None,
    date_from: date | None = None,
    date_to: date | None = None,
    ball_type: str | None = None,
) -> FullAnalytics:
    """Get complete analytics for a profile — one API call, all insights."""

    club_summaries = await get_club_summaries(
        db, profile_id,
        date_from=date_from, date_to=date_to,
        club_name=club_name, ball_type=ball_type,
    )
    session_trends = await get_session_trends(
        db, profile_id,
        club_name=club_name, date_from=date_from,
        date_to=date_to, ball_type=ball_type,
    )
    improvement = await get_improvement_summary(
        db, profile_id, club_name=club_name,
    )
    handicap = await estimate_handicap(db, profile_id)

    return FullAnalytics(
        club_summaries=club_summaries,
        session_trends=session_trends,
        improvement_summary=improvement,
        handicap_estimate=handicap,
    )
