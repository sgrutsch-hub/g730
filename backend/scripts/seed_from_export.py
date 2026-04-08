"""
Seed the database from a cleaned Swing Doctor export CSV.

Usage:
    cd backend
    python -m scripts.seed_from_export --csv PATH --profile-id UUID [--dry-run]

Deletes ALL existing sessions/shots for the profile, then imports
the cleaned CSV with corrected dates and shot scores.
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import sys
import uuid
from collections import defaultdict
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import _get_session_factory, dispose_engine
from app.models.session import Session
from app.models.shot import Shot
from app.services.processing import process_session_shots


def _dec(val: str) -> Decimal | None:
    if not val or val.strip() == "":
        return None
    try:
        return Decimal(val.strip())
    except InvalidOperation:
        return None


def _int(val: str) -> int | None:
    d = _dec(val)
    return int(d) if d is not None else None


SOURCE_FORMAT_MAP = {
    "Square LM": "bushnell_dr",
    "Foresight": "bushnell_sa",
    "Foresight (via SD)": "bushnell_sa",
    "Swing Doctor": "bushnell_sa",
}


async def seed(csv_path: str, profile_id: uuid.UUID, dry_run: bool) -> None:
    # Read CSV
    with open(csv_path) as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    print(f"Read {len(rows)} rows from {csv_path}")

    # Group by date
    sessions_data: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        sessions_data[row["Date"]].append(row)

    print(f"Found {len(sessions_data)} sessions by date")

    if dry_run:
        for date_str, shots in sorted(sessions_data.items()):
            clubs = defaultdict(int)
            for s in shots:
                clubs[s["Club"]] += 1
            club_str = ", ".join(f"{c}:{n}" for c, n in sorted(clubs.items()))
            print(f"  {date_str}: {len(shots)} shots ({club_str})")
        print("\nDry run — no changes made.")
        return

    factory = _get_session_factory()
    async with factory() as db:  # type: AsyncSession
        # Delete existing sessions for this profile (CASCADE deletes shots)
        result = await db.execute(
            select(func.count()).select_from(Session).where(
                Session.profile_id == profile_id
            )
        )
        existing_count = result.scalar()
        print(f"Deleting {existing_count} existing sessions for profile {profile_id}...")

        await db.execute(
            delete(Session).where(Session.profile_id == profile_id)
        )
        await db.flush()

        # Create sessions and shots
        total_shots = 0
        for date_str in sorted(sessions_data.keys()):
            shot_rows = sessions_data[date_str]

            # Parse date: MM-DD-YYYY
            parts = date_str.split("-")
            session_date = date(int(parts[2]), int(parts[0]), int(parts[1]))

            # Determine source format from first row's Source column
            first_source = shot_rows[0].get("Source", "")
            source_format = SOURCE_FORMAT_MAP.get(first_source, "bushnell_sa")

            session = Session(
                profile_id=profile_id,
                source_file=f"seed_{date_str}",
                source_format=source_format,
                session_date=session_date,
                shot_count=len(shot_rows),
                imported_at=datetime.now(timezone.utc),
                ball_type=shot_rows[0].get("Ball Type") or None,
            )
            db.add(session)
            await db.flush()  # get session.id

            for idx, row in enumerate(shot_rows):
                shot = Shot(
                    session_id=session.id,
                    profile_id=profile_id,
                    club_name=row["Club"],
                    shot_index=idx,
                    shot_date=session_date,
                    ball_speed_mph=_dec(row.get("Ball Speed", "")),
                    club_speed_mph=_dec(row.get("Club Speed", "")),
                    smash_factor=_dec(row.get("Smash Factor", "")),
                    carry_yards=_dec(row.get("Carry", "")),
                    total_yards=_dec(row.get("Total", "")),
                    offline_yards=_dec(row.get("Offline", "")),
                    launch_angle_deg=_dec(row.get("Launch Angle", "")),
                    spin_rate_rpm=_int(row.get("Spin Rate", "")),
                    spin_axis_deg=_dec(row.get("Spin Axis", "")),
                    attack_angle_deg=_dec(row.get("Attack Angle", "")),
                    club_path_deg=_dec(row.get("Club Path", "")),
                    face_angle_deg=_dec(row.get("Face Angle", "")),
                    dynamic_loft_deg=_dec(row.get("Dynamic Loft", "")),
                    apex_feet=_dec(row.get("Apex", "")),
                    landing_angle_deg=_dec(row.get("Landing Angle", "")),
                    ball_type=row.get("Ball Type") or None,
                    is_filtered=row.get("Filtered", "Yes") == "Yes",
                )
                db.add(shot)

            total_shots += len(shot_rows)

            # Process: theoretical carry + trim + shot score
            await process_session_shots(db, session)

            clubs = defaultdict(int)
            for r in shot_rows:
                clubs[r["Club"]] += 1
            club_str = ", ".join(f"{c}:{n}" for c, n in sorted(clubs.items()))
            print(f"  {date_str}: {len(shot_rows)} shots ({club_str})")

        await db.commit()
        print(f"\nSeeded {len(sessions_data)} sessions, {total_shots} shots.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed database from cleaned export CSV")
    parser.add_argument("--csv", required=True, help="Path to cleaned CSV file")
    parser.add_argument("--profile-id", required=True, help="Profile UUID to seed")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be imported without changes")
    args = parser.parse_args()

    try:
        pid = uuid.UUID(args.profile_id)
    except ValueError:
        print(f"ERROR: Invalid UUID: {args.profile_id}", file=sys.stderr)
        sys.exit(1)

    try:
        asyncio.run(seed(args.csv, pid, args.dry_run))
    finally:
        asyncio.run(dispose_engine())


if __name__ == "__main__":
    main()
