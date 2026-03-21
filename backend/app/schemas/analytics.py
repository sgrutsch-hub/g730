from __future__ import annotations

"""Pydantic schemas for analytics API responses."""

from datetime import date
from decimal import Decimal

from pydantic import BaseModel


class ClubSummaryResponse(BaseModel):
    club_name: str
    shot_count: int
    session_count: int
    avg_carry: Decimal | None = None
    min_carry: Decimal | None = None
    max_carry: Decimal | None = None
    std_carry: Decimal | None = None
    avg_ball_speed: Decimal | None = None
    max_ball_speed: Decimal | None = None
    avg_club_speed: Decimal | None = None
    avg_spin_rate: int | None = None
    avg_launch_angle: Decimal | None = None
    avg_offline: Decimal | None = None
    std_offline: Decimal | None = None
    left_miss_pct: Decimal | None = None
    right_miss_pct: Decimal | None = None
    avg_smash: Decimal | None = None
    avg_apex: Decimal | None = None
    avg_landing_angle: Decimal | None = None


class SessionTrendResponse(BaseModel):
    session_date: date
    shot_count: int
    avg_carry: Decimal | None = None
    avg_ball_speed: Decimal | None = None
    avg_spin_rate: int | None = None
    avg_offline: Decimal | None = None
    avg_smash: Decimal | None = None
    avg_launch_angle: Decimal | None = None


class TrendSummaryResponse(BaseModel):
    metric: str
    current: Decimal | None = None
    previous: Decimal | None = None
    delta: Decimal | None = None
    direction: str = "flat"


class HandicapEstimateResponse(BaseModel):
    estimated_low: Decimal
    estimated_high: Decimal
    confidence: str
    factors: list[str]
    total_shots: int
    unique_clubs: int


class FullAnalyticsResponse(BaseModel):
    club_summaries: list[ClubSummaryResponse]
    session_trends: list[SessionTrendResponse]
    improvement_summary: list[TrendSummaryResponse]
    handicap_estimate: HandicapEstimateResponse | None = None
