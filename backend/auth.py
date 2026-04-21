"""HTTP Bearer / API-key authentication for Buddi backend.

Implements SEC-02 — every router in ``backend.api`` depends on
``require_api_client`` so that no endpoint can be reached without a valid
credential. Two credential modes are supported:

  * ``API_KEY`` env var — a single shared secret for server-to-server calls.
  * ``SECRET_KEY`` env var — HMAC key for signed bearer tokens
    (future JWT use; for now the API_KEY path is the active mechanism).

If neither ``API_KEY`` nor ``SECRET_KEY`` is configured, the dependency
refuses every request with HTTP 503, on the principle that it is safer to
be unreachable than publicly accessible.
"""

from __future__ import annotations

import hmac
import os
from typing import Optional

from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from core.config import settings

bearer_scheme = HTTPBearer(auto_error=False)


def _constant_time_eq(a: str, b: str) -> bool:
    return hmac.compare_digest(a.encode("utf-8"), b.encode("utf-8"))


async def require_api_client(
    request: Request,
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
) -> str:
    """Router-level dependency that enforces authentication on every route.

    Returns the resolved client identifier (``"api-key"`` or the bearer
    subject). Raises HTTP 401 on missing/invalid credentials.
    """
    api_key = settings.API_KEY or os.getenv("API_KEY")
    secret = settings.SECRET_KEY

    # 1) Static API-key header: ``X-API-Key`` or ``Authorization: Bearer <key>``.
    header_key = request.headers.get("x-api-key")
    if api_key:
        if header_key and _constant_time_eq(header_key, api_key):
            return "api-key"
        if credentials and credentials.scheme.lower() == "bearer" and _constant_time_eq(
            credentials.credentials, api_key
        ):
            return "api-key"

    # 2) Signed bearer token (reserved for future JWT rollout).
    if credentials and credentials.scheme.lower() == "bearer" and secret:
        # Minimal check: the token must at least match the server secret until
        # a full JWT implementation is introduced. This keeps the surface
        # area narrow instead of silently accepting unsigned tokens.
        if _constant_time_eq(credentials.credentials, secret):
            return "bearer"

    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Authentication required",
        headers={"WWW-Authenticate": "Bearer"},
    )
