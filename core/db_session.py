"""Tenant-scoped DB session dependency (Sprint 1 multi-tenant safety).

Buddi enforces tenant isolation at three layers:

  1. **Application** — every query in ``backend/api.py`` explicitly filters
     by ``tenant_id`` (this has been true since v4.0).
  2. **Auth boundary** — ``backend/auth.py:require_api_client`` stamps the
     tenant UUID onto ``request.state.tenant_id`` so handlers can never
     guess.
  3. **Database** — Postgres row-level security policies on every
     tenant-scoped table (see the RLS migration). This is the defense-in-
     depth layer that catches a missing application-side filter before it
     leaks PHI across tenants.

This module is the bridge between layers (2) and (3). It opens a normal
``SessionLocal()``, then for every request sets the Postgres
``app.tenant_id`` GUC to the authenticated tenant. The RLS policies are
written against ``current_setting('app.tenant_id')`` so the database
itself refuses to return another tenant's rows even if the application
forgets a ``WHERE tenant_id = ...`` clause.

The session is exposed as a FastAPI dependency:

    @app.get("/api/something")
    async def endpoint(db: Session = Depends(tenant_scoped_session)):
        ...

A handful of unauthenticated endpoints (``/health``, ``/internal/health``)
also depend on this — for those we explicitly clear the GUC so any
accidental query inside the handler raises a policy violation rather
than silently returning rows.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any, Generator, Optional

from fastapi import Request
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy.sql import text

from core.database import SessionLocal

logger = logging.getLogger(__name__)


def _coerce_tenant_id(value: Any) -> Optional[uuid.UUID]:
    """Best-effort coercion of any tenant marker to UUID."""

    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError):
        return None


def set_tenant_context(db: Session, tenant_id: Optional[uuid.UUID]) -> None:
    """Stamp the tenant UUID onto Postgres's ``app.tenant_id`` GUC.

    ``set_config(..., true)`` scopes the value to the current transaction
    so each request gets its own isolated context. Setting an empty
    string explicitly clears the GUC; this is what ``/health`` and other
    unauthenticated routes do, ensuring RLS-protected queries inside
    them fail closed rather than open.
    """

    payload = "" if tenant_id is None else str(tenant_id)
    try:
        db.execute(text("SELECT set_config('app.tenant_id', :val, true)"), {"val": payload})
    except SQLAlchemyError as e:
        # We log but do not raise — the application-side filter still runs
        # and tenant isolation is preserved. RLS provides defense in
        # depth, not the sole defense. The audit log records the
        # degraded state via the route handler's own observability.
        logger.warning(
            "Failed to set Postgres app.tenant_id GUC (RLS defense-in-depth degraded): %s",
            e,
        )


def tenant_scoped_session(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that yields an RLS-scoped DB session.

    The tenant UUID is read from ``request.state.tenant_id`` which is
    populated by :func:`backend.auth.require_api_client`. Routes that
    bypass auth (``/health``) still depend on this, and for those the
    GUC is explicitly cleared.
    """

    tenant_id = _coerce_tenant_id(getattr(request.state, "tenant_id", None))
    db = SessionLocal()
    try:
        set_tenant_context(db, tenant_id)
        yield db
    finally:
        try:
            # Clear the GUC on the connection before returning it to the
            # pool so a subsequent borrow cannot accidentally inherit a
            # stale tenant context.
            set_tenant_context(db, None)
        except Exception:
            pass
        db.close()


__all__ = ["set_tenant_context", "tenant_scoped_session"]
