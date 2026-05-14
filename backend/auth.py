"""HTTP Bearer / API-key authentication for Buddi backend.

Sprint 1 multi-tenancy replaces the former plaintext env-var comparison with
per-tenant API keys stored in Postgres. Incoming keys are looked up by a
deterministic SHA-256 digest, then verified against a salted Argon2 hash.
"""

from __future__ import annotations

import hmac
import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.exc import SQLAlchemyError

try:  # pragma: no cover - exercised indirectly when dependency is installed
    from argon2 import PasswordHasher
    from argon2.exceptions import VerifyMismatchError, VerificationError
except Exception:  # pragma: no cover - keeps test-mode fallback importable
    PasswordHasher = None  # type: ignore[assignment]
    VerifyMismatchError = VerificationError = Exception  # type: ignore[misc,assignment]

from core.config import settings
from core.database import SessionLocal
from core.models import TenantApiKey

bearer_scheme = HTTPBearer(auto_error=False)
_password_hasher = PasswordHasher() if PasswordHasher is not None else None


class AuthenticatedClient(str):
    """String-compatible auth result with tenant metadata attached."""

    tenant_id: uuid.UUID | None
    scopes: list[str]
    api_key_id: uuid.UUID | None

    def __new__(
        cls,
        value: str,
        *,
        tenant_id: uuid.UUID | None = None,
        scopes: list[str] | None = None,
        api_key_id: uuid.UUID | None = None,
    ):
        obj = str.__new__(cls, value)
        obj.tenant_id = tenant_id
        obj.scopes = scopes or []
        obj.api_key_id = api_key_id
        return obj


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


def api_key_lookup_hash(api_key: str) -> str:
    """Deterministic digest used for indexed tenant-api-key lookup."""

    return hashlib.sha256(api_key.encode("utf-8")).hexdigest()


def hash_api_key(api_key: str) -> str:
    """Create a salted Argon2 hash for storage in ``tenant_api_keys``."""

    if _password_hasher is None:
        raise RuntimeError("argon2-cffi is required to hash tenant API keys")
    return _password_hasher.hash(api_key)


def verify_api_key_hash(api_key: str, hashed_key: str) -> bool:
    if _password_hasher is None:
        return False
    try:
        return bool(_password_hasher.verify(hashed_key, api_key))
    except (VerifyMismatchError, VerificationError, Exception):
        return False


def _presented_api_key(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials],
) -> str | None:
    header_key = request.headers.get("x-api-key")
    if header_key:
        return header_key
    if credentials and credentials.scheme.lower() == "bearer":
        return credentials.credentials
    return None


def _test_mode_static_fallback(request: Request, presented_key: str | None) -> AuthenticatedClient | None:
    """Preserve offline HTTP-layer tests without allowing prod plaintext auth."""

    if os.getenv("ENVIRONMENT", "production").lower() == "production":
        return None  # Security: never allow plaintext test-mode API-key fallback in production.
    api_key = settings.API_KEY or os.getenv("API_KEY")
    if os.getenv("BUDDI_TEST_MODE") != "1" or not api_key or not presented_key:
        return None
    if not _constant_time_eq(presented_key, api_key):
        return None
    fallback_tid = uuid.UUID("00000000-0000-0000-0000-000000000001")
    request.state.tenant_id = fallback_tid
    request.state.scopes = ["test", "clinician", "admin", "ingest"]
    request.state.api_key_id = None
    return AuthenticatedClient("api-key", tenant_id=fallback_tid, scopes=request.state.scopes)


async def require_api_client(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> AuthenticatedClient:
    """Router-level dependency that enforces authentication on every route.

    Returns a string-compatible client identifier with ``tenant_id`` and
    ``scopes`` attributes. Raises HTTP 401 on missing/invalid credentials.
    """
    presented_key = _presented_api_key(request, credentials)

    # 1) Tenant API-key header: ``X-API-Key`` or ``Authorization: Bearer <key>``.
    if presented_key:
        db = SessionLocal()
        try:
            key_row = (
                db.query(TenantApiKey)
                .filter(TenantApiKey.key_hash_sha256 == api_key_lookup_hash(presented_key))
                .first()
            )
            now = datetime.now(timezone.utc)
            if (
                key_row
                and (key_row.expires_at is None or key_row.expires_at > now)
                and verify_api_key_hash(presented_key, key_row.hashed_key)
            ):
                key_row.last_used_at = now
                db.commit()
                scopes = list(key_row.scopes or [])
                request.state.tenant_id = key_row.tenant_id
                request.state.scopes = scopes
                request.state.api_key_id = key_row.id
                return AuthenticatedClient(
                    f"tenant:{key_row.tenant_id}",
                    tenant_id=key_row.tenant_id,
                    scopes=scopes,
                    api_key_id=key_row.id,
                )
        except SQLAlchemyError:
            db.rollback()
            fallback = _test_mode_static_fallback(request, presented_key)
            if fallback is not None:
                return fallback
        finally:
            db.close()

        fallback = _test_mode_static_fallback(request, presented_key)
        if fallback is not None:
            return fallback

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )


def require_scope(required_scope: str):
    async def _check(client: AuthenticatedClient = Depends(require_api_client)):
        # Security: enforce least-privilege scopes after authentication succeeds.
        if required_scope not in client.scopes:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Scope '{required_scope}' is required for this endpoint.",
            )
        return client

    return _check
