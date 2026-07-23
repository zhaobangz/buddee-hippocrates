"""Shared PHI processing precondition checks."""

from __future__ import annotations

import logging
import os
import uuid
from datetime import datetime, timezone

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core import models

logger = logging.getLogger(__name__)


class PHIProcessingNotAllowed(RuntimeError):
    """Raised when real PHI would enter an unapproved processing path."""


# C-2: break-glass requires dual control. BOTH flags must be disabled — a
# single compromised CI variable or mistaken ops runbook can no longer lift
# the PHI gates on its own.
_BREAKGLASS_FLAGS = (
    "BUDDI_PHI_PROCESSING_ENFORCEMENT",
    "BUDDI_BAA_INGEST_ENFORCEMENT",
)
_breakglass_alerted = False


def _breakglass_until_valid() -> bool:
    """True only when ``BUDDI_BREAKGLASS_UNTIL`` is a future ISO-8601 stamp.

    Break-glass must be time-bounded: an ops runbook that forgets to turn the
    bypass back off self-heals at the deadline instead of running ungated
    forever. Missing or malformed values fail closed.
    """

    raw = os.getenv("BUDDI_BREAKGLASS_UNTIL", "").strip()
    if not raw:
        return False
    try:
        until = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except ValueError:
        logger.error(
            "BUDDI_BREAKGLASS_UNTIL=%r is not valid ISO-8601 — ignoring break-glass.",
            raw,
        )
        return False
    if until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)
    return datetime.now(timezone.utc) < until


def _disabled_by_breakglass() -> bool:
    """Break-glass bypass — active only under dual control and a time bound.

    All of the following must hold (audit C-2):
      1. BOTH ``BUDDI_PHI_PROCESSING_ENFORCEMENT`` and
         ``BUDDI_BAA_INGEST_ENFORCEMENT`` are set to ``disabled``;
      2. ``BUDDI_BREAKGLASS_UNTIL`` is a future ISO-8601 timestamp;
      3. when ``ENVIRONMENT=production`` (the safe default when unset),
         ``BUDDI_ALLOW_PROD_BREAKGLASS=1`` is also set.

    Every activation logs CRITICAL once per process so the alarm fires in
    Cloud Logging even if nobody is watching the request path.
    """

    global _breakglass_alerted
    if not all(os.getenv(flag, "").strip().lower() == "disabled" for flag in _BREAKGLASS_FLAGS):
        return False
    if not _breakglass_until_valid():
        return False
    if os.getenv("ENVIRONMENT", "production").strip().lower() == "production":
        if os.getenv("BUDDI_ALLOW_PROD_BREAKGLASS", "").strip() != "1":
            return False
    if not _breakglass_alerted:
        _breakglass_alerted = True
        logger.critical(
            "BREAK-GLASS ACTIVE: PHI/BAA enforcement disabled until %s. "
            "Clinical processing is running WITHOUT BAA gates — page on-call "
            "and track per docs/INCIDENT_RESPONSE.md.",
            os.getenv("BUDDI_BREAKGLASS_UNTIL"),
        )
    return True


def breakglass_active() -> bool:
    """Public probe for startup checks / ops dashboards (see backend/api.py)."""

    return _disabled_by_breakglass()


def global_baa_confirmed() -> bool:
    """True when provider-level BAA readiness has been explicitly confirmed."""

    return os.getenv("BUDDI_BAA_CONFIRMED", "").strip() == "1"


def tenant_baa_confirmed(db: Session, tenant_id: uuid.UUID) -> bool:
    try:
        return bool(
            db.query(models.Tenant.baa_confirmed)
            .filter(models.Tenant.id == tenant_id)
            .scalar()
        )
    except SQLAlchemyError:
        logger.error(
            "DB error checking tenant BAA status for %s — failing closed",
            tenant_id,
            exc_info=True,
        )
        return False


def assert_phi_processing_allowed(
    db: Session,
    tenant_id: uuid.UUID,
    *,
    synthetic: bool = False,
) -> None:
    """Fail closed unless synthetic/demo data or both BAA gates are confirmed."""

    if synthetic:
        return
    if _disabled_by_breakglass():
        logger.warning(
            "PHI/BAA enforcement bypassed by break-glass for tenant=%s",
            tenant_id,
        )
        return
    if not global_baa_confirmed():
        raise PHIProcessingNotAllowed(
            "Global provider BAA confirmation is missing. Set BUDDI_BAA_CONFIRMED=1 "
            "only after the provider BAA is fully executed."
        )
    if not tenant_baa_confirmed(db, tenant_id):
        raise PHIProcessingNotAllowed(
            "Tenant BAA confirmation is missing. Real PHI cannot be processed until "
            "tenants.baa_confirmed is TRUE for this tenant."
        )


def payload_is_synthetic(payload: dict | None) -> bool:
    """Return True only for payloads explicitly stamped synthetic by API code."""

    return bool((payload or {}).get("synthetic") is True)


__all__ = [
    "PHIProcessingNotAllowed",
    "assert_phi_processing_allowed",
    "breakglass_active",
    "global_baa_confirmed",
    "payload_is_synthetic",
    "tenant_baa_confirmed",
]
