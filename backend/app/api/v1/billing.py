from __future__ import annotations

"""Billing API endpoints — Stripe checkout, portal, webhooks."""

from fastapi import APIRouter, Depends, Header, Request
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.database import get_db
from app.dependencies import get_current_user
from app.models.user import User
from app.services.billing import (
    create_billing_portal_session,
    create_checkout_session,
    handle_webhook_event,
)

router = APIRouter(prefix="/billing", tags=["billing"])


# ── Schemas ──


class CheckoutRequest(BaseModel):
    price_id: str
    success_url: str = "https://swing.doctor/billing/success"
    cancel_url: str = "https://swing.doctor/billing/cancel"


class CheckoutResponse(BaseModel):
    checkout_url: str


class PortalRequest(BaseModel):
    return_url: str = "https://swing.doctor/profile"


class PortalResponse(BaseModel):
    portal_url: str


class SubscriptionStatusResponse(BaseModel):
    tier: str
    is_active: bool
    stripe_customer_id: str | None = None


# ── Endpoints ──


@router.post(
    "/checkout",
    response_model=CheckoutResponse,
    summary="Create Stripe Checkout session",
)
async def checkout(
    body: CheckoutRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> CheckoutResponse:
    """
    Create a Stripe Checkout Session for upgrading to Pro or Pro+.

    Returns a URL to redirect the user to Stripe's hosted checkout page.
    After successful payment, Stripe fires a webhook to update the tier.
    """
    url = await create_checkout_session(
        db, user,
        price_id=body.price_id,
        success_url=body.success_url,
        cancel_url=body.cancel_url,
    )
    return CheckoutResponse(checkout_url=url)


@router.post(
    "/portal",
    response_model=PortalResponse,
    summary="Open Stripe Billing Portal",
)
async def billing_portal(
    body: PortalRequest,
    user: User = Depends(get_current_user),
) -> PortalResponse:
    """
    Create a Stripe Billing Portal session.

    Allows users to manage their subscription, update payment method,
    view invoices, and cancel.
    """
    url = await create_billing_portal_session(
        user, return_url=body.return_url,
    )
    return PortalResponse(portal_url=url)


@router.get(
    "/status",
    response_model=SubscriptionStatusResponse,
    summary="Current subscription status",
)
async def subscription_status(
    user: User = Depends(get_current_user),
) -> SubscriptionStatusResponse:
    """Get the current user's subscription tier and status."""
    return SubscriptionStatusResponse(
        tier=user.subscription_tier,
        is_active=user.subscription_tier != "free",
        stripe_customer_id=user.stripe_customer_id,
    )


@router.post("/webhook", include_in_schema=False)
async def stripe_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict:
    """
    Stripe webhook receiver.

    This endpoint is called by Stripe to notify us of subscription events.
    It verifies the webhook signature and processes the event.

    Not included in the API docs — only Stripe should call this.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    result = await handle_webhook_event(db, payload, sig_header)
    return result
