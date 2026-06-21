"""Tests for the PROMPT_04 Stripe billing integration.

All Stripe calls are mocked — no real Stripe API calls or keys. The billing
helpers are unit-tested against transient ``Tenant`` ORM instances + a MagicMock
session; the HTTP surface is tested via the TestClient (auth/scoping + webhook
signature rejection).
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
import stripe

from backend import billing
from core.models import Tenant


def _tenant(**kw) -> Tenant:
    return Tenant(id=uuid.uuid4(), name=kw.pop("name", "Test Clinic"), **kw)


def _mock_db_returning(tenant) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter_by.return_value.first.return_value = tenant
    return db


# ---------------------------------------------------------------------------
# billing.py helpers
# ---------------------------------------------------------------------------


def test_get_or_create_customer_creates():
    tenant = _tenant()
    assert tenant.stripe_customer_id is None
    db = MagicMock()
    with patch("stripe.Customer.create", return_value=SimpleNamespace(id="cus_123")) as create:
        cid = billing.get_or_create_customer(db, tenant)
    create.assert_called_once()
    assert cid == "cus_123"
    assert tenant.stripe_customer_id == "cus_123"


def test_get_or_create_customer_existing():
    tenant = _tenant(stripe_customer_id="cus_existing")
    db = MagicMock()
    with patch("stripe.Customer.create") as create:
        cid = billing.get_or_create_customer(db, tenant)
    create.assert_not_called()
    assert cid == "cus_existing"


def test_create_checkout_session():
    tenant = _tenant(stripe_customer_id="cus_1", physician_count=3)
    db = MagicMock()
    with patch(
        "stripe.checkout.Session.create",
        return_value=SimpleNamespace(url="https://checkout.stripe/abc"),
    ):
        url = billing.create_checkout_session(db, tenant, "https://ok", "https://no")
    assert url == "https://checkout.stripe/abc"


def test_create_portal_session():
    tenant = _tenant(stripe_customer_id="cus_1")
    db = MagicMock()
    with patch(
        "stripe.billing_portal.Session.create",
        return_value=SimpleNamespace(url="https://portal.stripe/xyz"),
    ):
        url = billing.create_portal_session(db, tenant, "https://return")
    assert url == "https://portal.stripe/xyz"


def test_webhook_invoice_paid():
    tenant = _tenant(subscription_id="sub_123")
    db = _mock_db_returning(tenant)
    invoice = SimpleNamespace(
        subscription="sub_123",
        lines=SimpleNamespace(data=[SimpleNamespace(period=SimpleNamespace(end=1_700_000_000))]),
    )
    event = SimpleNamespace(type="invoice.paid", data=SimpleNamespace(object=invoice))
    with patch("stripe.Webhook.construct_event", return_value=event):
        result = billing.handle_webhook_event(db, b"{}", "sig")
    assert result == {"processed": True, "event_type": "invoice.paid"}
    assert tenant.subscription_status == "active"
    assert tenant.subscription_current_period_end is not None


def test_webhook_subscription_deleted():
    tenant = _tenant(subscription_id="sub_456", subscription_status="active")
    db = _mock_db_returning(tenant)
    sub = SimpleNamespace(id="sub_456")
    event = SimpleNamespace(type="customer.subscription.deleted", data=SimpleNamespace(object=sub))
    with patch("stripe.Webhook.construct_event", return_value=event):
        result = billing.handle_webhook_event(db, b"{}", "sig")
    assert result["event_type"] == "customer.subscription.deleted"
    assert tenant.subscription_status == "canceled"


def test_webhook_invalid_signature():
    db = MagicMock()
    err = stripe.error.SignatureVerificationError("bad sig", "sig-header")
    with patch("stripe.Webhook.construct_event", side_effect=err):
        with pytest.raises(stripe.error.SignatureVerificationError):
            billing.handle_webhook_event(db, b"{}", "sig-header")


# ---------------------------------------------------------------------------
# HTTP surface
# ---------------------------------------------------------------------------


def test_api_billing_subscribe_401(client):
    resp = client.post("/api/billing/subscribe", json={})
    assert resp.status_code == 401


def test_api_billing_subscribe_403(client, auth_headers):
    # Test-mode key carries only ["test", "clinician"] — not admin -> 403.
    resp = client.post("/api/billing/subscribe", headers=auth_headers, json={})
    assert resp.status_code == 403


def test_api_billing_webhook_bad_sig(client):
    resp = client.post(
        "/api/billing/webhook",
        content=b'{"type": "invoice.paid"}',
        headers={"stripe-signature": "t=1,v1=deadbeef", "content-type": "application/json"},
    )
    assert resp.status_code == 400
