"""Tests for the build-out B2 webhook dispatch.

Covers HMAC-SHA256 signing, event filtering, audit logging, and secret
encryption-at-rest — all without a live DB or network (the SQLAlchemy session
is a MagicMock and the SMART/customer HTTP server is an httpx.MockTransport).
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import uuid
from unittest.mock import MagicMock

import httpx
import pytest

from core import webhooks
from core.models import WebhookEndpoint
from core.storage import SecureStorage

SECRET = "whsec_test_0123456789abcdef"
TENANT = uuid.UUID("00000000-0000-0000-0000-000000000001")


def _endpoint(events, url="https://example.test/hook") -> WebhookEndpoint:
    enc = SecureStorage().encrypt_blob(SECRET)
    return WebhookEndpoint(
        id=uuid.uuid4(),
        tenant_id=TENANT,
        url=url,
        secret=base64.b64encode(enc).decode("ascii"),
        events=list(events),
        active=True,
    )


def _fake_db(endpoints) -> MagicMock:
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = endpoints
    return db


def test_sign_payload_matches_reference_hmac():
    body = webhooks.canonical_body(webhooks.EVENT_HCC_CREATED, {"a": 1})
    assert webhooks.sign_payload(SECRET, body) == hmac.new(
        SECRET.encode(), body, hashlib.sha256
    ).hexdigest()


def test_register_webhook_rejects_unknown_event():
    with pytest.raises(ValueError, match="Unknown webhook event"):
        webhooks.register_webhook(MagicMock(), TENANT, "https://x.test", ["bogus.event"], SECRET)


def test_register_webhook_rejects_private_url():
    with pytest.raises(ValueError, match="non-public|not permitted"):
        webhooks.register_webhook(
            MagicMock(),
            TENANT,
            "https://127.0.0.1/hook",
            [webhooks.EVENT_HCC_CREATED],
            SECRET,
        )


def test_register_webhook_encrypts_secret_at_rest():
    # The stored secret must be recoverable (for HMAC) but never plaintext.
    enc = SecureStorage().encrypt_blob(SECRET)
    stored = base64.b64encode(enc).decode("ascii")
    assert SECRET not in stored
    assert webhooks._decrypt_secret(stored, None) == SECRET


@pytest.mark.asyncio
async def test_dispatch_signs_and_fires_for_subscribed_event():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["sig"] = request.headers.get("X-Buddi-Signature")
        captured["event"] = request.headers.get("X-Buddi-Event")
        captured["body"] = request.content
        return httpx.Response(200, json={"ok": True})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db = _fake_db([_endpoint([webhooks.EVENT_HCC_CREATED])])
    audit_calls = []

    def audit_logger(_db, event_type, payload_data, tenant_id=None, **_):
        audit_calls.append(event_type)

    payload = {"codes": ["E11.22"]}
    results = await webhooks.dispatch_webhook(
        db,
        TENANT,
        webhooks.EVENT_HCC_CREATED,
        payload,
        http_client=client,
        audit_logger=audit_logger,
    )

    expected = "sha256=" + webhooks.sign_payload(
        SECRET, webhooks.canonical_body(webhooks.EVENT_HCC_CREATED, payload)
    )
    assert captured["sig"] == expected
    assert captured["event"] == webhooks.EVENT_HCC_CREATED
    assert captured["body"] == webhooks.canonical_body(webhooks.EVENT_HCC_CREATED, payload)
    assert results[0]["ok"] is True
    assert audit_calls == ["webhook.delivered"]


@pytest.mark.asyncio
async def test_dispatch_skips_unsubscribed_event():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not POST to an unsubscribed endpoint")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db = _fake_db([_endpoint([webhooks.EVENT_HCC_APPROVED])])
    results = await webhooks.dispatch_webhook(
        db, TENANT, webhooks.EVENT_HCC_CREATED, {}, http_client=client
    )
    assert results == []


@pytest.mark.asyncio
async def test_dispatch_records_failure_without_raising():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db = _fake_db([_endpoint([webhooks.EVENT_AUDIT_FLAGGED])])
    audit_calls = []

    def audit_logger(_db, event_type, payload_data, tenant_id=None, **_):
        audit_calls.append(event_type)

    results = await webhooks.dispatch_webhook(
        db,
        TENANT,
        webhooks.EVENT_AUDIT_FLAGGED,
        {"risk": "high"},
        http_client=client,
        audit_logger=audit_logger,
    )
    assert results[0]["ok"] is False
    assert audit_calls == ["webhook.failed"]


@pytest.mark.asyncio
async def test_dispatch_blocks_private_url_without_posting():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("must not POST to an unsafe endpoint")

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    db = _fake_db([_endpoint([webhooks.EVENT_HCC_CREATED], url="https://127.0.0.1/hook")])
    audit_calls = []

    def audit_logger(_db, event_type, payload_data, tenant_id=None, **_):
        audit_calls.append(event_type)

    results = await webhooks.dispatch_webhook(
        db,
        TENANT,
        webhooks.EVENT_HCC_CREATED,
        {},
        http_client=client,
        audit_logger=audit_logger,
    )
    assert results[0]["ok"] is False
    assert audit_calls == ["webhook.failed"]
