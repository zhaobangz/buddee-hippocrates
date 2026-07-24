"""Portal user-auth primitives: JWT sessions, roles, password policy.

Human portal users authenticate with email + password + hCaptcha (see
``backend/auth_users.py``); a successful login issues a short-lived HS256
access JWT plus a rotating refresh token (``AuthRefreshToken`` row).

Key-derivation note: if ``BUDDI_JWT_SECRET`` is set it signs JWTs directly;
otherwise a domain-separated key is derived from ``SECRET_KEY`` via
HMAC-SHA256 so portal tokens can never be confused with anything else
signed by the primary secret, and existing deployments keep working
without a new mandatory env var.
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

import jwt

from core.config import settings

JWT_ALGORITHM = "HS256"
JWT_ISSUER = "buddi-portal"
JWT_AUDIENCE = "buddi-portal-web"

# Role → scopes, resolved at login and baked into the JWT. Kept deliberately
# small; machine integrations keep using TenantApiKey scopes.
ROLE_SCOPES: Dict[str, List[str]] = {
    "admin": ["clinician", "ingest", "admin"],
    "clinician": ["clinician"],
    "billing": ["clinician"],
}
KNOWN_ROLES = frozenset(ROLE_SCOPES)

# Online brute-force policy: N consecutive failures → 15-minute lock.
MAX_FAILED_LOGINS = 5
LOCKOUT_MINUTES = 15

MIN_PASSWORD_LENGTH = 12
# Tiny static denylist — the top passwords in every breach corpus. Length and
# rate limiting do the heavy lifting; this catches the worst offenders.
_COMMON_PASSWORDS = frozenset(
    {
        "password1234",
        "password12345",
        "qwertyuiop12",
        "123456789012",
        "111111111111",
        "iloveyou1234",
        "adminadmin12",
        "letmein12345",
    }
)

_DUMMY_HASH_PRECOMPUTED: Optional[str] = None


def normalize_email(email: str) -> str:
    """Canonical form stored in ``users.email`` (unique constraint is plain,
    so case-insensitivity is enforced by normalising at write time)."""

    return (email or "").strip().lower()


def validate_password(password: str) -> Optional[str]:
    """Return an error string when the password violates policy, else None."""

    if not password:
        return "Password is required."
    if len(password) < MIN_PASSWORD_LENGTH:
        return f"Password must be at least {MIN_PASSWORD_LENGTH} characters."
    if password.lower() in _COMMON_PASSWORDS:
        return "That password is too common — pick something harder to guess."
    if len(set(password)) == 1:
        return "Password cannot be a single repeated character."
    if not re.search(r"[a-zA-Z]", password) or not re.search(r"[0-9]", password):
        return "Password must contain at least one letter and one digit."
    return None


def _signing_key() -> str:
    """HS256 key for portal JWTs (dedicated secret or domain-separated)."""

    dedicated = (settings.BUDDI_JWT_SECRET or "").strip()
    if dedicated:
        return dedicated
    return hmac.new(
        settings.SECRET_KEY.encode("utf-8"),
        b"buddi-portal-jwt-signing-v1",
        hashlib.sha256,
    ).hexdigest()


def issue_access_token(
    *,
    user_id: uuid.UUID,
    tenant_id: uuid.UUID,
    role: str,
    session_id: uuid.UUID,
) -> tuple[str, int]:
    """Mint a short-lived access JWT. Returns ``(token, expires_in_seconds)``."""

    now = datetime.now(timezone.utc)
    expires = now + timedelta(minutes=settings.BUDDI_JWT_ACCESS_MINUTES)
    claims = {
        "sub": str(user_id),
        "tenant_id": str(tenant_id),
        "role": role,
        "scopes": ROLE_SCOPES.get(role, ["clinician"]),
        "sid": str(session_id),
        "iss": JWT_ISSUER,
        "aud": JWT_AUDIENCE,
        "iat": int(now.timestamp()),
        "exp": int(expires.timestamp()),
        "jti": secrets.token_hex(16),
    }
    token = jwt.encode(claims, _signing_key(), algorithm=JWT_ALGORITHM)
    return token, int(settings.BUDDI_JWT_ACCESS_MINUTES * 60)


def verify_access_token(token: str) -> Optional[Dict[str, Any]]:
    """Verify an access JWT. Returns claims on success, None on any failure.

    Fails closed on expiry, tampering, wrong key, and algorithm confusion —
    PyJWT requires an explicit algorithm whitelist, so ``alg=none`` and
    RS/HS confusion attempts raise inside ``jwt.decode``.
    """

    try:
        claims = jwt.decode(
            token,
            _signing_key(),
            algorithms=[JWT_ALGORITHM],
            issuer=JWT_ISSUER,
            audience=JWT_AUDIENCE,
            options={"require": ["exp", "iat", "sub", "tenant_id"]},
        )
    except jwt.PyJWTError:
        return None
    if claims.get("role") not in KNOWN_ROLES:
        return None
    return claims



def generate_refresh_token() -> str:
    """New opaque refresh token (URL-safe, 256 bits of entropy)."""

    return secrets.token_urlsafe(32)


def refresh_token_digest(token: str) -> str:
    """SHA-256 digest stored in ``auth_refresh_tokens.token_hash``."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def invite_token_digest(token: str) -> str:
    """SHA-256 digest stored in ``tenant_invites.token_hash``."""

    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generate_invite_token() -> str:
    """New opaque invite token (URL-safe, 256 bits of entropy)."""

    return secrets.token_urlsafe(32)


def dummy_password_verify(verify_fn) -> None:
    """Run an Argon2 verify against a fixed dummy hash.

    Called on the "email not found" login path so unknown accounts cost the
    same ~100ms as known ones — the response must not reveal whether the
    email exists (user-enumeration resistance).
    """

    global _DUMMY_HASH_PRECOMPUTED
    from backend.auth import hash_api_key  # pinned Argon2id hasher

    if _DUMMY_HASH_PRECOMPUTED is None:
        _DUMMY_HASH_PRECOMPUTED = hash_api_key("buddi-dummy-password-for-timing")
    verify_fn("buddi-dummy-password-for-timing-x", _DUMMY_HASH_PRECOMPUTED)


__all__ = [
    "JWT_ALGORITHM",
    "KNOWN_ROLES",
    "LOCKOUT_MINUTES",
    "MAX_FAILED_LOGINS",
    "MIN_PASSWORD_LENGTH",
    "ROLE_SCOPES",
    "dummy_password_verify",
    "generate_invite_token",
    "generate_refresh_token",
    "invite_token_digest",
    "issue_access_token",
    "normalize_email",
    "refresh_token_digest",
    "validate_password",
    "verify_access_token",
]
