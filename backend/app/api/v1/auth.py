from __future__ import annotations

"""
Auth routes — registration, login, token refresh.

These are the only unauthenticated endpoints. Everything else
requires a valid access token via the get_current_user dependency.
"""

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.database import get_db
from app.schemas.auth import (
    LoginRequest,
    RefreshRequest,
    RegisterRequest,
    TokenResponse,
    UserResponse,
)
from app.services.auth import login_user, refresh_tokens, register_user
from app.services.email import (
    reset_password,
    send_password_reset_email,
    send_verification_email,
    verify_email_token,
)

settings = get_settings()
router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=TokenResponse, status_code=201)
async def register(body: RegisterRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Create a new user account.

    Returns JWT tokens on success. A default golfer profile is
    automatically created with the user's display name.
    """
    user, access_token, refresh_token = await register_user(
        db,
        email=body.email,
        password=body.password,
        display_name=body.display_name,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/login", response_model=TokenResponse)
async def login(body: LoginRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Authenticate with email and password.

    Returns JWT tokens on success. The access token should be included
    in subsequent requests as: Authorization: Bearer <token>
    """
    user, access_token, refresh_token = await login_user(
        db,
        email=body.email,
        password=body.password,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.post("/refresh", response_model=TokenResponse)
async def refresh(body: RefreshRequest, db: AsyncSession = Depends(get_db)) -> TokenResponse:
    """
    Exchange a refresh token for new access + refresh tokens.

    Call this when the access token expires. The old refresh token
    is invalidated and a new pair is issued.
    """
    access_token, refresh_token = await refresh_tokens(
        db,
        refresh_token=body.refresh_token,
    )
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


# ── Email verification ──


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    new_password: str


@router.post("/verify-email", summary="Verify email address")
async def verify_email(
    body: VerifyEmailRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Verify a user's email using the token from the verification email."""
    user = await verify_email_token(db, body.token)
    return {"verified": True, "email": user.email}


@router.post("/forgot-password", summary="Request password reset")
async def forgot_password(
    body: ForgotPasswordRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """
    Send a password reset email.

    Always returns success to prevent email enumeration.
    """
    await send_password_reset_email(db, body.email)
    return {"sent": True}


@router.post("/reset-password", summary="Reset password with token")
async def reset_password_endpoint(
    body: ResetPasswordRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Reset a user's password using the token from the reset email."""
    await reset_password(db, body.token, body.new_password)
    return {"reset": True}
