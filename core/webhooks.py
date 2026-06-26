"""Customer webhooks for prior-auth and HCC events (build-out B2).

Strategy-doc §2.1 gap #8: billing customers need webhooks on day one. This
module registers customer endpoints and dispatches HMAC-signed event payloads
to them.

Security:
  * The signing secret is stored **encrypted at rest** (``SecureStorage`` /
    BUDDI_STORAGE_KEY), base64-wrapped into the ``webhook_endpoints.secret``
    TEXT column. Outgoing payloads are signed with HMAC-SHA256 using the *raw*
    secret (recovered by decrypting), which the customer verifies with their
    copy. (A one-way Argon2 hash could not be used to sign — see the model
    docstring.)
  * Dispatch is best-effort with a hard 5s timeout per endpoint and never
    raises into the request path; every attempt is recorded to ``audit_events``
    via the injected ``audit_logger`` (``backend.api.log_audit_event_postgres``),
    keeping the single-audit-source rule (no third-party analytics).

``dispatch_webhook`` takes an injectable ``http_client`` and ``audit_logger`` so
the whole path is unit-testable without network or a live audit DB.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import uuid
from typing import Any, Callable, Dict, List, Optional, Sequence

import httpx

from core.models import WebhookEndpoint
from core.outbound_security import validate_outbound_url
from core.storage import SecureStorage

logger = logging.getLogger(__name__)

WEBHOOK_TIMEOUT_SECONDS = 5.0

# The four event types the platform emits (build-out B2.3).
EVENT_PRIOR_AUTH_CHANGED = "prior_auth_state.changed"
EVENT_HCC_CREATED = "hcc_suggestion.created"
EVENT_HCC_APPROVED = "hcc_suggestion.approved"
EVENT_AUDIT_FLAGGED = "audit_event.flagged"

KNOWN_EVENTS = frozenset(
    {
        EVENT_PRIOR_AUTH_CHANGED,
        EVENT_HCC_CREATED,
        EVENT_HCC_APPROVED,
        EVENT_AUDIT_FLAGGED,
    }
)

AuditLogger = Callable[..., Any]


def _storage(storage: Optional[SecureStorage]) -> SecureStorage:
    return storage or SecureStorage()


def canonical_body(event_type: str, payload: Dict[str, Any]) -> bytes:
    """Deterministic JSON body so the signature is reproducible by the customer."""

    return json.dumps(
        {"event": event_type, "data": payload},
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sign_payload(secret: str, body: bytes) -> str:
    """HMAC-SHA256 hex digest of ``body`` under the raw signing ``secret``."""

    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def register_webhook(
    db,
    tenant_id: uuid.UUID,
    url: str,
    events: Sequence[str],
    secret: str,
    *,
    storage: Optional[SecureStorage] = None,
) -> WebhookEndpoint:
    """Create a webhook registration, storing the secret encrypted at rest."""

    unknown = sorted(set(events) - KNOWN_EVENTS)
    if unknown:
        raise ValueError(f"Unknown webhook event(s): {', '.join(unknown)}")
    if not events:
        raise ValueError("At least one event type is required.")
    safe_url = validate_outbound_url(url)

    encrypted = _storage(storage).encrypt_blob(secret)
    row = WebhookEndpoint(
        tenant_id=tenant_id,
        url=safe_url,
        secret=base64.b64encode(encrypted).decode("ascii"),
        events=list(events),
        active=True,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def _decrypt_secret(stored: str, storage: Optional[SecureStorage]) -> str:
    return _storage(storage).decrypt_blob(base64.b64decode(stored))


async def dispatch_webhook(
    db,
    tenant_id: uuid.UUID,
    event_type: str,
    payload: Dict[str, Any],
    *,
    audit_logger: Optional[AuditLogger] = None,
    http_client: Optional[httpx.AsyncClient] = None,
    storage: Optional[SecureStorage] = None,
) -> List[Dict[str, Any]]:
    """Sign and POST ``payload`` to every active endpoint subscribed to ``event_type``.

    Returns a per-endpoint result list. Never raises into the caller — delivery
    failures are logged to ``audit_events`` and returned with ``ok=False``.
    """

    try:
        endpoints = (
            db.query(WebhookEndpoint)
            .filter(
                WebhookEndpoint.tenant_id == tenant_id,
                WebhookEndpoint.active.is_(True),
            )
            .all()
        )
    except Exception as e:  # noqa: BLE001 - DB offline must not break the request
        logger.warning("Webhook endpoint lookup failed: %s", e)
        return []

    targets = [ep for ep in endpoints if event_type in (ep.events or [])]
    if not targets:
        return []

    body = canonical_body(event_type, payload)
    results: List[Dict[str, Any]] = []
    own_client = http_client is None
    client = http_client or httpx.AsyncClient(
        timeout=WEBHOOK_TIMEOUT_SECONDS,
        follow_redirects=False,
    )
    try:
        for ep in targets:
            status_code: Optional[int] = None
            ok = False
            try:
                safe_url = validate_outbound_url(ep.url)
                secret = _decrypt_secret(ep.secret, storage)
                signature = sign_payload(secret, body)
                resp = await client.post(
                    safe_url,
                    content=body,
                    headers={
                        "Content-Type": "application/json",
                        "X-Buddi-Event": event_type,
                        "X-Buddi-Signature": f"sha256={signature}",
                    },
                    timeout=WEBHOOK_TIMEOUT_SECONDS,
                    follow_redirects=False,
                )
                status_code = resp.status_code
                ok = 200 <= resp.status_code < 300
            except Exception as e:  # noqa: BLE001 - any delivery failure is non-fatal
                logger.warning("Webhook delivery to %s failed: %s", ep.url, e)

            if audit_logger is not None:
                try:
                    audit_logger(
                        db,
                        event_type="webhook.delivered" if ok else "webhook.failed",
                        payload_data={
                            "webhook_id": str(ep.id),
                            "event": event_type,
                            "status_code": status_code,
                            "ok": ok,
                        },
                        tenant_id=str(tenant_id),
                    )
                except Exception as e:  # noqa: BLE001 - audit failure is non-fatal here
                    logger.warning("Webhook audit log failed: %s", e)

            results.append({"webhook_id": str(ep.id), "ok": ok, "status_code": status_code})
    finally:
        if own_client:
            await client.aclose()
    return results
