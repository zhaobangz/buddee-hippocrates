"""Stripe billing integration for Buddee (PROMPT_04).

All functions take an explicit db session and the tenant. No function reads or
writes Stripe secret keys (or card data) to logs or DB rows — only the Stripe
customer/subscription IDs and a coarse subscription status are persisted.

Pricing model (strategy-doc §2.4): flat $250–400/physician/month OR a 15–20%
gain-share on validated recovered revenue, whichever is greater.
"""

from datetime import datetime, timezone

import stripe
from sqlalchemy.orm import Session

from core.config import settings
from core.models import Tenant

stripe.api_key = settings.STRIPE_SECRET_KEY


def get_or_create_customer(db: Session, tenant: Tenant) -> str:
    """
    Returns the Stripe customer ID for the tenant, creating one if needed.
    Stores stripe_customer_id on the tenant row.
    Customer metadata: {"tenant_id": str(tenant.id), "tenant_name": tenant.name}
    """
    if tenant.stripe_customer_id:
        return tenant.stripe_customer_id
    customer = stripe.Customer.create(
        name=tenant.name,
        metadata={"tenant_id": str(tenant.id), "tenant_name": tenant.name},
    )
    tenant.stripe_customer_id = customer.id
    db.commit()
    return customer.id


def create_checkout_session(db: Session, tenant: Tenant, success_url: str, cancel_url: str) -> str:
    """
    Creates a Stripe Checkout session for the monthly subscription.
    Returns the checkout URL. The customer is redirected there by the frontend.
    """
    customer_id = get_or_create_customer(db, tenant)
    session = stripe.checkout.Session.create(
        customer=customer_id,
        mode="subscription",
        line_items=[{"price": settings.STRIPE_PRICE_ID_MONTHLY, "quantity": tenant.physician_count or 1}],
        success_url=success_url,
        cancel_url=cancel_url,
        metadata={"tenant_id": str(tenant.id)},
    )
    return session.url


def create_portal_session(db: Session, tenant: Tenant, return_url: str) -> str:
    """
    Creates a Stripe billing portal session so the customer can manage
    their subscription, update payment methods, and view invoices.
    Returns the portal URL.
    """
    customer_id = get_or_create_customer(db, tenant)
    portal = stripe.billing_portal.Session.create(
        customer=customer_id,
        return_url=return_url,
    )
    return portal.url


def handle_webhook_event(db: Session, payload: bytes, sig_header: str) -> dict:
    """
    Validates Stripe webhook signature and processes the event.
    Returns {"processed": True, "event_type": event.type} on success.
    Raises stripe.error.SignatureVerificationError on invalid signature.
    """
    event = stripe.Webhook.construct_event(
        payload, sig_header, settings.STRIPE_WEBHOOK_SECRET
    )

    if event.type == "invoice.paid":
        subscription_id = event.data.object.subscription
        _on_invoice_paid(db, subscription_id, event.data.object)

    elif event.type == "customer.subscription.deleted":
        subscription_id = event.data.object.id
        _on_subscription_deleted(db, subscription_id)

    elif event.type == "customer.subscription.updated":
        _on_subscription_updated(db, event.data.object)

    return {"processed": True, "event_type": event.type}


def _on_invoice_paid(db: Session, subscription_id: str, invoice) -> None:
    """Set subscription_status='active' for the tenant with this subscription."""
    tenant = db.query(Tenant).filter_by(subscription_id=subscription_id).first()
    if tenant:
        tenant.subscription_status = "active"
        tenant.subscription_current_period_end = datetime.fromtimestamp(
            invoice.lines.data[0].period.end, tz=timezone.utc
        )
        db.commit()


def _on_subscription_deleted(db: Session, subscription_id: str) -> None:
    """Set subscription_status='canceled'."""
    tenant = db.query(Tenant).filter_by(subscription_id=subscription_id).first()
    if tenant:
        tenant.subscription_status = "canceled"
        db.commit()


def _on_subscription_updated(db: Session, subscription) -> None:
    """Sync status and period end from Stripe subscription object."""
    tenant = db.query(Tenant).filter_by(subscription_id=subscription.id).first()
    if tenant:
        tenant.subscription_status = subscription.status
        tenant.subscription_current_period_end = datetime.fromtimestamp(
            subscription.current_period_end, tz=timezone.utc
        )
        db.commit()
