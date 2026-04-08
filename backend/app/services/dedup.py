from __future__ import annotations

"""
Shot-level deduplication service.

Detects duplicate shots by matching (date, club_name, ball_speed_mph)
and finds existing sessions to merge new shots into.
"""

import uuid
from datetime import date
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.session import Session
from app.models.shot import Shot


async def find_duplicate_shots(
    db: AsyncSession,
    profile_id: uuid.UUID,
    session_date: date,
) -> set[tuple[str, Decimal]]:
    """
    Return set of (club_name, ball_speed_mph) tuples that already exist
    for this profile on this date. Used to skip re-inserting duplicates.
    """
    result = await db.execute(
        select(Shot.club_name, Shot.ball_speed_mph)
        .where(Shot.profile_id == profile_id, Shot.shot_date == session_date)
    )
    return {(row[0], row[1]) for row in result.all() if row[1] is not None}


async def find_existing_session_for_date(
    db: AsyncSession,
    profile_id: uuid.UUID,
    session_date: date,
) -> Session | None:
    """Find an existing session for this profile and date to merge into."""
    result = await db.execute(
        select(Session)
        .where(Session.profile_id == profile_id, Session.session_date == session_date)
        .order_by(Session.imported_at)
        .limit(1)
    )
    return result.scalar_one_or_none()


async def get_max_shot_index(
    db: AsyncSession,
    session_id: uuid.UUID,
) -> int:
    """Get the highest shot_index in a session (for appending new shots)."""
    from sqlalchemy import func
    result = await db.execute(
        select(func.coalesce(func.max(Shot.shot_index), -1))
        .where(Shot.session_id == session_id)
    )
    return result.scalar() or -1
