from __future__ import annotations

"""
Shot processing pipeline — trimming, theoretical carry, and computed fields.

This runs after CSV parsing and shot insertion. It applies the bottom-N%
carry trim and computes theoretical carry distances using physics simulation.
"""

import math
from collections import defaultdict
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.shot import Shot

# ── 15-handicap ideal parameters per club for shot scoring ──
IRON_IDEALS: dict[str, dict[str, float]] = {
    "5 Iron":  {"carry": 170, "offline_tol": 15, "ball_speed": 120, "launch_angle": 14.0, "spin_rate": 5000, "smash_factor": 1.38, "attack_angle": -2.5},
    "6 Iron":  {"carry": 160, "offline_tol": 14, "ball_speed": 115, "launch_angle": 16.0, "spin_rate": 5500, "smash_factor": 1.37, "attack_angle": -3.0},
    "7 Iron":  {"carry": 148, "offline_tol": 13, "ball_speed": 110, "launch_angle": 18.0, "spin_rate": 6200, "smash_factor": 1.36, "attack_angle": -3.5},
    "8 Iron":  {"carry": 137, "offline_tol": 12, "ball_speed": 105, "launch_angle": 20.0, "spin_rate": 7000, "smash_factor": 1.34, "attack_angle": -4.0},
    "9 Iron":  {"carry": 125, "offline_tol": 11, "ball_speed": 100, "launch_angle": 23.0, "spin_rate": 7800, "smash_factor": 1.33, "attack_angle": -4.3},
    "PW":      {"carry": 115, "offline_tol": 10, "ball_speed": 94,  "launch_angle": 25.5, "spin_rate": 8600, "smash_factor": 1.31, "attack_angle": -4.5},
    "GW":      {"carry": 105, "offline_tol": 9,  "ball_speed": 88,  "launch_angle": 28.0, "spin_rate": 9200, "smash_factor": 1.29, "attack_angle": -4.8},
}

# Scoring weights: carry + offline = 80%, everything else = 20%
_SCORE_COMPONENTS = [
    # (ideal_key, tolerance, weight, use_absolute)
    ("carry",        30,   0.40, False),
    ("offline_tol",  None,  0.40, True),   # tolerance = the ideal value itself
    ("ball_speed",   20,   0.05, False),
    ("launch_angle", 8,    0.05, False),
    ("spin_rate",    2500, 0.04, False),
    ("smash_factor", 0.15, 0.03, False),
    ("attack_angle", 5,    0.03, False),
]

# Map ideal keys to Shot model attribute names
_IDEAL_TO_SHOT_ATTR = {
    "carry": "carry_yards",
    "offline_tol": "offline_yards",
    "ball_speed": "ball_speed_mph",
    "launch_angle": "launch_angle_deg",
    "spin_rate": "spin_rate_rpm",
    "smash_factor": "smash_factor",
    "attack_angle": "attack_angle_deg",
}


def _compute_shot_score(shot: Shot) -> Decimal | None:
    """Compute weighted performance score (0-100) for an iron shot."""
    ideal = IRON_IDEALS.get(shot.club_name)
    if not ideal:
        return None

    total_score = 0.0
    total_weight = 0.0

    for ideal_key, tolerance, weight, use_abs in _SCORE_COMPONENTS:
        attr = _IDEAL_TO_SHOT_ATTR[ideal_key]
        val = getattr(shot, attr, None)
        if val is None:
            continue

        actual = float(val)
        if use_abs:
            # Offline: ideal is 0, tolerance is the club's offline_tol value
            actual = abs(actual)
            ideal_val = 0.0
            tol = float(ideal["offline_tol"])
        else:
            ideal_val = float(ideal[ideal_key])
            tol = float(tolerance)

        diff = abs(actual - ideal_val)
        penalty = min(diff / tol, 1.0) if tol > 0 else (0.0 if diff == 0 else 1.0)
        total_score += (1.0 - penalty) * weight
        total_weight += weight

    if total_weight <= 0:
        return None

    score = (total_score / total_weight) * 100
    return Decimal(str(round(score, 1)))


async def process_session_shots(
    db: AsyncSession,
    session: Session,
    club_targets: dict[str, Decimal] | None = None,
    trim_pct: float = 0.20,
    elevation_ft: int = 0,
) -> None:
    """
    Process all shots in a session:
      1. Compute theoretical carry for each shot
      2. Apply target-based trim (or bottom-N% fallback)

    This modifies shots in-place within the current transaction.
    Caller is responsible for committing.

    Args:
        db: Active database session
        session: The session whose shots need processing
        club_targets: Mapping of club name → target carry yards.
                      Clubs with a target use +/-15% window trim.
                      Clubs without a target fall back to bottom-N% trim.
        trim_pct: Bottom percentage to trim for clubs without targets (default 20%)
        elevation_ft: Elevation for air density adjustment in physics sim
    """
    result = await db.execute(
        select(Shot)
        .where(Shot.session_id == session.id)
        .order_by(Shot.shot_index)
    )
    shots = list(result.scalars().all())
    if not shots:
        return

    if club_targets is None:
        club_targets = {}

    # Step 1: Compute theoretical carry for each shot
    for shot in shots:
        shot.theoretical_carry = _theoretical_carry(
            ball_speed_mph=shot.ball_speed_mph,
            launch_angle_deg=shot.launch_angle_deg,
            spin_rate_rpm=shot.spin_rate_rpm,
            elevation_ft=elevation_ft,
        )

    # Step 2: Null out bogus club speed (smash factor > 1.55 is physically impossible)
    for shot in shots:
        if (shot.club_speed_mph and shot.club_speed_mph > 0
                and shot.ball_speed_mph and shot.ball_speed_mph > 0):
            smash = shot.ball_speed_mph / shot.club_speed_mph
            if smash > Decimal("1.55"):
                shot.club_speed_mph = None

    # Step 3: Apply trim, grouped by club
    clubs: dict[str, list[Shot]] = defaultdict(list)
    for shot in shots:
        clubs[shot.club_name].append(shot)

    for club_name, club_shots in clubs.items():
        target = club_targets.get(club_name)
        if target:
            _apply_target_trim(club_shots, target)
        else:
            _apply_trim(club_shots, trim_pct)

    # Step 4: Compute shot score for iron shots
    for shot in shots:
        shot.shot_score = _compute_shot_score(shot)

    # Update processed timestamp
    from sqlalchemy import func
    session.processed_at = func.now()


def _apply_target_trim(shots: list[Shot], target: Decimal, window: float = 0.15) -> None:
    """
    Target-based trim: keep shots within +/- window% of the target carry.

    Example: target=138, window=0.15 → keep shots with carry in [117.3, 158.7].
    Shots with no carry data are filtered out.
    """
    lo = target * Decimal(str(1 - window))
    hi = target * Decimal(str(1 + window))

    for shot in shots:
        if shot.carry_yards is None or shot.carry_yards <= 0:
            shot.is_filtered = False
        else:
            shot.is_filtered = lo <= shot.carry_yards <= hi


def _apply_trim(shots: list[Shot], trim_pct: float) -> None:
    """
    Hybrid trim: mark shots as outliers if they fall in the bottom N%
    by ball speed OR by carry distance.

    This catches both thin/mishit shots (low ball speed, low carry) AND
    ballooned shots (decent speed but high spin → short carry) that a
    single-metric trim would miss.

    Shots with no carry or no ball speed data are marked as filtered out.
    """
    # Need both carry and ball speed for hybrid trim
    valid = [
        s for s in shots
        if s.carry_yards is not None and s.carry_yards > 0
        and s.ball_speed_mph is not None and s.ball_speed_mph > 0
    ]

    if not valid:
        for s in shots:
            s.is_filtered = False
        return

    # Find cutoff for carry (bottom N%)
    by_carry = sorted(valid, key=lambda s: s.carry_yards)  # type: ignore[arg-type]
    carry_cutoff_idx = int(len(by_carry) * trim_pct)
    carry_cutoff = by_carry[carry_cutoff_idx].carry_yards if carry_cutoff_idx < len(by_carry) else Decimal("0")

    # Find cutoff for ball speed (bottom N%)
    by_speed = sorted(valid, key=lambda s: s.ball_speed_mph)  # type: ignore[arg-type]
    speed_cutoff_idx = int(len(by_speed) * trim_pct)
    speed_cutoff = by_speed[speed_cutoff_idx].ball_speed_mph if speed_cutoff_idx < len(by_speed) else Decimal("0")

    # Mark each shot — must pass BOTH thresholds to be included
    for shot in shots:
        if (shot.carry_yards is None or shot.carry_yards <= 0
                or shot.ball_speed_mph is None or shot.ball_speed_mph <= 0):
            shot.is_filtered = False
        else:
            shot.is_filtered = (
                shot.carry_yards >= carry_cutoff
                and shot.ball_speed_mph >= speed_cutoff
            )


def _theoretical_carry(
    ball_speed_mph: Decimal | None,
    launch_angle_deg: Decimal | None,
    spin_rate_rpm: int | None,
    elevation_ft: int = 0,
) -> Decimal | None:
    """
    Physics-based carry distance estimation.

    Uses a simplified trajectory simulation accounting for:
    - Drag force (quadratic)
    - Lift force (from backspin via Magnus effect)
    - Air density adjusted for elevation
    - Gravity

    This matches the PWA's theoreticalCarry() function exactly.

    Args:
        ball_speed_mph: Initial ball speed in mph
        launch_angle_deg: Launch angle in degrees
        spin_rate_rpm: Total spin rate in RPM
        elevation_ft: Course/range elevation in feet

    Returns:
        Estimated carry distance in yards, or None if inputs are invalid
    """
    if not ball_speed_mph or ball_speed_mph <= 0:
        return None
    if not launch_angle_deg or launch_angle_deg <= 0:
        return None
    if not spin_rate_rpm or spin_rate_rpm <= 0:
        return None

    bs = float(ball_speed_mph)
    la = float(launch_angle_deg)
    sr = float(spin_rate_rpm)

    # Air density adjustment for elevation
    rho = 1.225 * math.exp(-elevation_ft * 0.3048 / 8500)
    dr = rho / 1.225

    # Convert to SI units
    v = bs * 0.44704  # mph to m/s
    theta = math.radians(la)

    vx = v * math.cos(theta)
    vy = v * math.sin(theta)

    # Golf ball physical constants
    mass = 0.04593  # kg
    radius = 0.02135  # m
    area = math.pi * radius * radius

    # Aerodynamic coefficients (adjusted for air density)
    cd = 0.225 * dr  # Drag coefficient
    cl = 0.00015 * sr / 1000 * dr  # Lift coefficient (spin-dependent)

    # Trajectory simulation (Euler method)
    x = 0.0
    y = 0.0
    dt = 0.01

    t = 0.0
    while t < 15.0:
        speed = math.sqrt(vx * vx + vy * vy)
        if speed == 0:
            break

        drag = 0.5 * rho * area * cd * speed
        lift = 0.5 * rho * area * cl * speed

        vx += (-drag * vx / mass) * dt
        vy += (-9.81 - drag * vy / mass + lift * speed / mass) * dt

        x += vx * dt
        y += vy * dt

        if y < 0 and t > 0.1:
            break

        t += dt

    # Convert meters to yards
    carry_yards = x / 0.9144
    return Decimal(str(round(carry_yards, 1)))
