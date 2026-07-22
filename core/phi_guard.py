"""Shared PHI processing precondition checks."""

from __future__ import annotations

import logging
import os
import uuid

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from core import models

logger = logging.getLogger(__name__)


class PHIProcessingNotAllowed(RuntimeError):
    """Raised when real PHI would enter an unapproved processing path."""


def _disabled_by_breakglass() -> bool:
    return (
        os.getenv("BUDDI_PHI_PROCESSING_ENFORCEMENT", "").strip().lower() == "disabled"
        or os.getenv("BUDDI_BAA_INGEST_ENFORCEMENT", "").strip().lower() == "disabled"
    )


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
    "global_baa_confirmed",
    "payload_is_synthetic",
    "tenant_baa_confirmed",
]
