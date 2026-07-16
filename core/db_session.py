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
from sqlalchemy import event
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


def set_worker_context(db: Session, enabled: bool) -> None:
    """Stamp the queue-worker marker used by the jobs RLS policy."""

    payload = "1" if enabled else ""
    try:
        db.execute(text("SELECT set_config('app.worker_mode', :val, true)"), {"val": payload})
    except SQLAlchemyError as e:
        logger.warning(
            "Failed to set Postgres app.worker_mode GUC (worker jobs RLS degraded): %s",
            e,
        )


class GucStamper:
    """Re-stamp the RLS GUCs at the start of *every* transaction on a session.

    ``set_config(..., true)`` is **transaction**-scoped: the first
    ``COMMIT``/``ROLLBACK`` on the session silently clears ``app.tenant_id``.
    Any handler that commits mid-request (the audit logger does, on nearly
    every route) would leave the remainder of the request running with an
    empty GUC — under ``FORCE ROW LEVEL SECURITY`` that means every later
    SELECT returns zero rows and every later INSERT/UPDATE fails its
    ``WITH CHECK``. Tests never see this because they run on SQLite.

    The fix is the canonical multi-tenant RLS pattern: hook the session's
    ``after_begin`` event and re-issue the transaction-local ``set_config``
    each time a new transaction begins. This preserves the fail-closed
    default (a pooled connection carries no GUC between requests) while
    surviving any number of mid-request commits.
    """

    def __init__(self, tenant_id: Optional[uuid.UUID] = None, worker_mode: bool = False):
        self.tenant_id = tenant_id
        self.worker_mode = worker_mode

    # -- listener --------------------------------------------------------
    def _after_begin(self, session: Session, transaction, connection) -> None:
        # Savepoints (nested transactions) inherit the enclosing
        # transaction's GUCs — only stamp real top-level transactions.
        if getattr(transaction, "nested", False):
            return
        if connection.dialect.name != "postgresql":
            return  # SQLite/tests: RLS does not exist; nothing to stamp.
        try:
            connection.execute(
                text("SELECT set_config('app.tenant_id', :val, true)"),
                {"val": "" if self.tenant_id is None else str(self.tenant_id)},
            )
            connection.execute(
                text("SELECT set_config('app.worker_mode', :val, true)"),
                {"val": "1" if self.worker_mode else ""},
            )
        except SQLAlchemyError as e:
            logger.warning("GUC re-stamp failed (RLS defense-in-depth degraded): %s", e)

    # -- lifecycle -------------------------------------------------------
    def install(self, db: Session) -> None:
        event.listen(db, "after_begin", self._after_begin)
        # Stamp the current/first transaction immediately as well.
        set_tenant_context(db, self.tenant_id)
        set_worker_context(db, self.worker_mode)

    def remove(self, db: Session) -> None:
        try:
            event.remove(db, "after_begin", self._after_begin)
        except Exception:  # listener may already be gone on teardown paths
            pass

    def set_tenant(self, db: Session, tenant_id: Optional[uuid.UUID]) -> None:
        """Switch the stamped tenant (worker loop reuses one session per job)."""

        self.tenant_id = tenant_id
        set_tenant_context(db, tenant_id)


def tenant_scoped_session(request: Request) -> Generator[Session, None, None]:
    """FastAPI dependency that yields an RLS-scoped DB session.

    The tenant UUID is read from ``request.state.tenant_id`` which is
    populated by :func:`backend.auth.require_api_client`. Routes that
    bypass auth (``/health``) still depend on this, and for those the
    GUC is explicitly cleared.

    The GUC is (re-)stamped at every transaction start via
    :class:`GucStamper`, so mid-request commits cannot strip the RLS
    context from the remainder of the request.
    """

    tenant_id = _coerce_tenant_id(getattr(request.state, "tenant_id", None))
    db = SessionLocal()
    stamper = GucStamper(tenant_id=tenant_id, worker_mode=False)
    try:
        stamper.install(db)
        yield db
    finally:
        stamper.remove(db)
        try:
            # Clear the GUC on the connection before returning it to the
            # pool so a subsequent borrow cannot accidentally inherit a
            # stale tenant context.
            set_tenant_context(db, None)
            set_worker_context(db, False)
        except Exception:
            pass
        db.close()


__all__ = [
    "GucStamper",
    "set_tenant_context",
    "set_worker_context",
    "tenant_scoped_session",
]
