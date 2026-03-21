from __future__ import annotations

"""
Email service — verification, password reset, and transactional emails.

Uses the `emails` library for simple, reliable email sending via SMTP.
Templates are inline (no external template files) for deployment simplicity.
"""

import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core.exceptions import AuthenticationError, NotFoundError, ValidationError
from app.models.user import User


def _create_verification_token(user_id: str, email: str) -> str:
    """Create a JWT token for email verification (expires in 24h)."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "email": email,
        "type": "email_verification",
        "exp": datetime.now(timezone.utc) + timedelta(hours=24),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _create_password_reset_token(user_id: str) -> str:
    """Create a JWT token for password reset (expires in 1h)."""
    settings = get_settings()
    payload = {
        "sub": user_id,
        "type": "password_reset",
        "exp": datetime.now(timezone.utc) + timedelta(hours=1),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


async def send_verification_email(user: User) -> None:
    """Send an email verification link to the user."""
    settings = get_settings()
    if not settings.smtp_host:
        # Skip in development — log instead
        import logging
        token = _create_verification_token(str(user.id), user.email)
        logging.getLogger(__name__).info(
            f"Verification email (SMTP not configured): "
            f"https://swing.doctor/verify?token={token}"
        )
        return

    import emails

    token = _create_verification_token(str(user.id), user.email)
    verify_url = f"https://swing.doctor/verify?token={token}"

    html = f"""
    <div style="font-family: -apple-system, system-ui, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1f2328;">Welcome to Swing Doctor</h2>
        <p>Hey {user.display_name or 'there'},</p>
        <p>Click below to verify your email address and start tracking your game:</p>
        <a href="{verify_url}"
           style="display: inline-block; background: #238636; color: #fff; padding: 12px 24px;
                  border-radius: 8px; text-decoration: none; font-weight: 600; margin: 16px 0;">
            Verify Email
        </a>
        <p style="color: #656d76; font-size: 13px; margin-top: 20px;">
            This link expires in 24 hours. If you didn't create a Swing Doctor account, ignore this email.
        </p>
    </div>
    """

    msg = emails.Message(
        subject="Verify your Swing Doctor account",
        html=html,
        mail_from=(settings.email_from, "Swing Doctor"),
    )

    msg.send(
        to=user.email,
        smtp={
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "user": settings.smtp_user,
            "password": settings.smtp_password,
            "tls": True,
        },
    )


async def verify_email_token(db: AsyncSession, token: str) -> User:
    """Verify an email verification token and activate the user."""
    settings = get_settings()

    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except Exception:
        raise ValidationError("Invalid or expired verification link")

    if payload.get("type") != "email_verification":
        raise ValidationError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise ValidationError("Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found")

    if user.is_verified:
        return user  # Already verified, idempotent

    user.is_verified = True
    user.verified_at = datetime.now(timezone.utc)
    await db.commit()

    return user


async def send_password_reset_email(db: AsyncSession, email: str) -> None:
    """Send a password reset link. Always succeeds (doesn't reveal if email exists)."""
    settings = get_settings()

    result = await db.execute(
        select(User).where(User.email == email.lower().strip())
    )
    user = result.scalar_one_or_none()

    if not user:
        return  # Silent — don't reveal whether email exists

    if not settings.smtp_host:
        import logging
        token = _create_password_reset_token(str(user.id))
        logging.getLogger(__name__).info(
            f"Password reset (SMTP not configured): "
            f"https://swing.doctor/reset-password?token={token}"
        )
        return

    import emails

    token = _create_password_reset_token(str(user.id))
    reset_url = f"https://swing.doctor/reset-password?token={token}"

    html = f"""
    <div style="font-family: -apple-system, system-ui, sans-serif; max-width: 500px; margin: 0 auto; padding: 20px;">
        <h2 style="color: #1f2328;">Reset Your Password</h2>
        <p>Hey {user.display_name or 'there'},</p>
        <p>Someone requested a password reset for your Swing Doctor account. Click below to set a new password:</p>
        <a href="{reset_url}"
           style="display: inline-block; background: #0969da; color: #fff; padding: 12px 24px;
                  border-radius: 8px; text-decoration: none; font-weight: 600; margin: 16px 0;">
            Reset Password
        </a>
        <p style="color: #656d76; font-size: 13px; margin-top: 20px;">
            This link expires in 1 hour. If you didn't request this, ignore this email — your password won't change.
        </p>
    </div>
    """

    msg = emails.Message(
        subject="Reset your Swing Doctor password",
        html=html,
        mail_from=(settings.email_from, "Swing Doctor"),
    )

    msg.send(
        to=user.email,
        smtp={
            "host": settings.smtp_host,
            "port": settings.smtp_port,
            "user": settings.smtp_user,
            "password": settings.smtp_password,
            "tls": True,
        },
    )


async def reset_password(
    db: AsyncSession, token: str, new_password: str
) -> User:
    """Reset a user's password using a valid reset token."""
    settings = get_settings()

    try:
        payload = jwt.decode(
            token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm]
        )
    except Exception:
        raise ValidationError("Invalid or expired reset link")

    if payload.get("type") != "password_reset":
        raise ValidationError("Invalid token type")

    user_id = payload.get("sub")
    if not user_id:
        raise ValidationError("Invalid token")

    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        raise NotFoundError("User not found")

    from app.core.security import hash_password
    user.password_hash = hash_password(new_password)
    await db.commit()

    return user
