from __future__ import annotations

"""Analytics API endpoints — club summaries, trends, handicap estimation."""

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.analytics.engine import (
    get_club_summaries,
    get_full_analytics,
    get_improvement_summary,
    get_session_trends,
    estimate_handicap,
)
from app.core.exceptions import AuthorizationError, NotFoundError
from app.database import get_db
from app.dependencies import get_current_user
from app.models.profile import Profile
from app.models.user import User
from app.schemas.analytics import (
    ClubSummaryResponse,
    FullAnalyticsResponse,
    HandicapEstimateResponse,
    SessionTrendResponse,
    TrendSummaryResponse,
)

router = APIRouter(prefix="/analytics", tags=["analytics"])


async def _get_owned_profile(
    profile_id: str, user: User, db: AsyncSession
) -> Profile:
    """Verify the profile belongs to the current user."""
    result = await db.execute(
        select(Profile).where(Profile.id == profile_id)
    )
    profile = result.scalar_one_or_none()
    if not profile:
        raise NotFoundError("Profile not found")
    if str(profile.user_id) != str(user.id):
        raise AuthorizationError("Not your profile")
    return profile


@router.get(
    "/profiles/{profile_id}/summary",
    response_model=FullAnalyticsResponse,
    summary="Full analytics bundle",
)
async def full_analytics(
    profile_id: str,
    club: str | None = Query(None, description="Filter to a single club"),
    date_from: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    date_to: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    ball_type: str | None = Query(None, description="Filter by ball type"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> FullAnalyticsResponse:
    """
    Get complete analytics for a profile — one call, all insights.

    Returns club summaries, session trends, improvement indicators,
    and handicap estimate.
    """
    await _get_owned_profile(profile_id, user, db)

    analytics = await get_full_analytics(
        db, profile_id,
        club_name=club, date_from=date_from,
        date_to=date_to, ball_type=ball_type,
    )

    return FullAnalyticsResponse(
        club_summaries=[
            ClubSummaryResponse(**s.__dict__) for s in analytics.club_summaries
        ],
        session_trends=[
            SessionTrendResponse(**t.__dict__) for t in analytics.session_trends
        ],
        improvement_summary=[
            TrendSummaryResponse(**i.__dict__) for i in analytics.improvement_summary
        ],
        handicap_estimate=(
            HandicapEstimateResponse(**analytics.handicap_estimate.__dict__)
            if analytics.handicap_estimate else None
        ),
    )


@router.get(
    "/profiles/{profile_id}/clubs",
    response_model=list[ClubSummaryResponse],
    summary="Per-club statistics",
)
async def club_summaries(
    profile_id: str,
    club: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    ball_type: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[ClubSummaryResponse]:
    """Per-club aggregate statistics (filtered shots only)."""
    await _get_owned_profile(profile_id, user, db)

    summaries = await get_club_summaries(
        db, profile_id,
        date_from=date_from, date_to=date_to,
        club_name=club, ball_type=ball_type,
    )
    return [ClubSummaryResponse(**s.__dict__) for s in summaries]


@router.get(
    "/profiles/{profile_id}/trends",
    response_model=list[SessionTrendResponse],
    summary="Session-over-session trends",
)
async def session_trends(
    profile_id: str,
    club: str | None = Query(None),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    ball_type: str | None = Query(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[SessionTrendResponse]:
    """Per-session averages over time for charting improvement."""
    await _get_owned_profile(profile_id, user, db)

    trends = await get_session_trends(
        db, profile_id,
        club_name=club, date_from=date_from,
        date_to=date_to, ball_type=ball_type,
    )
    return [SessionTrendResponse(**t.__dict__) for t in trends]


@router.get(
    "/profiles/{profile_id}/improvement",
    response_model=list[TrendSummaryResponse],
    summary="Are you improving?",
)
async def improvement(
    profile_id: str,
    club: str | None = Query(None),
    days: int = Query(30, ge=7, le=365, description="Lookback window in days"),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> list[TrendSummaryResponse]:
    """Compare recent vs earlier performance across key metrics."""
    await _get_owned_profile(profile_id, user, db)

    summary = await get_improvement_summary(
        db, profile_id,
        club_name=club, lookback_days=days,
    )
    return [TrendSummaryResponse(**s.__dict__) for s in summary]


@router.get(
    "/profiles/{profile_id}/handicap",
    response_model=HandicapEstimateResponse,
    summary="Estimated handicap potential",
)
async def handicap_estimate(
    profile_id: str,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> HandicapEstimateResponse:
    """
    Estimate handicap potential from shot data patterns.

    Uses 7 Iron carry, Driver carry, dispersion, smash factor, and
    bag coverage to estimate a handicap range. This is a practice-based
    estimate — actual handicap depends on short game and course management.
    """
    await _get_owned_profile(profile_id, user, db)

    estimate = await estimate_handicap(db, profile_id)
    if estimate is None:
        raise NotFoundError("No shot data available for handicap estimation")

    return HandicapEstimateResponse(**estimate.__dict__)
