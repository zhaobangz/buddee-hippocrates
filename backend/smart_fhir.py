"""SMART-on-FHIR App Launch (authorization code + PKCE).

Build-out B1 / strategy-doc §2.1 gap #2: the first real EHR connector. This
implements the standalone-launch half of the SMART App Launch Framework
against the SMART Health IT public sandbox (https://launch.smarthealthit.org)
for dev/staging, and any conformant FHIR R4 server in production.

Flow:
  1. ``begin_launch`` — generate a PKCE verifier/challenge + ``state``, persist
     them (encrypted) in a ``pending`` ehr_integrations row, and return the
     authorization URL the operator's browser is redirected to.
  2. ``complete_callback`` — on the OAuth redirect back, look the pending row
     up by ``state``, exchange the authorization code (+ PKCE verifier) for an
     access/refresh token at the token endpoint, store the tokens encrypted at
     rest, and mark the integration ``active``.
  3. ``fetch_patient_bundle`` — call the FHIR server with the bearer token and
     return an R4 Bundle.

The token/refresh material is encrypted with ``core/storage.SecureStorage``
(BUDDI_STORAGE_KEY) before it touches the ``ehr_integrations`` table, so the
DB never holds plaintext OAuth credentials.

Network calls go through an injectable ``httpx.AsyncClient`` so the whole flow
is unit-testable against a mocked SMART authorization server (see
tests/test_smart_fhir.py).
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import os
import secrets
import uuid
from dataclasses import dataclass
from typing import Any, Dict, Optional
from urllib.parse import urlencode

import httpx

from core.models import EhrIntegration
from core.storage import SecureStorage

logger = logging.getLogger(__name__)

# Defaults target the SMART Health IT public sandbox's R4 endpoint.
DEFAULT_FHIR_BASE_URL = "https://launch.smarthealthit.org/v/r4/fhir"
DEFAULT_SCOPE = "launch/patient patient/*.read offline_access openid fhirUser"


def _b64url_no_pad(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def generate_pkce() -> tuple[str, str]:
    """Return ``(code_verifier, code_challenge)`` for PKCE S256."""

    verifier = _b64url_no_pad(secrets.token_bytes(48))
    challenge = _b64url_no_pad(hashlib.sha256(verifier.encode("ascii")).digest())
    return verifier, challenge


def tenant_id_from_state(state: str) -> Optional[uuid.UUID]:
    """Extract the tenant UUID prefix from an opaque ``state`` value.

    ``state`` is ``"{tenant_id}.{random}"``. The tenant prefix lets the
    unauthenticated OAuth callback re-establish the RLS tenant context before
    it looks the pending row up; the random suffix remains the unguessable
    CSRF/authorization token. Returns None if the prefix is not a UUID.
    """

    head = state.split(".", 1)[0] if state else ""
    try:
        return uuid.UUID(head)
    except (TypeError, ValueError):
        return None


@dataclass
class SMARTEndpoints:
    authorization_endpoint: str
    token_endpoint: str


class SMARTFHIRLauncher:
    """Drives the SMART standalone-launch authorization-code + PKCE flow."""

    def __init__(
        self,
        *,
        client_id: Optional[str] = None,
        client_secret: Optional[str] = None,
        redirect_uri: Optional[str] = None,
        fhir_base_url: Optional[str] = None,
        http_client: Optional[httpx.AsyncClient] = None,
        storage: Optional[SecureStorage] = None,
    ):
        self.client_id = client_id or os.getenv("SMART_CLIENT_ID", "")
        self.client_secret = client_secret or os.getenv("SMART_CLIENT_SECRET", "")
        self.redirect_uri = redirect_uri or os.getenv(
            "SMART_REDIRECT_URI", "http://localhost:8001/api/ehr/callback"
        )
        self.fhir_base_url = (
            fhir_base_url or os.getenv("SMART_FHIR_BASE_URL", DEFAULT_FHIR_BASE_URL)
        ).rstrip("/")
        self._http = http_client
        self._storage = storage

    # ------------------------------------------------------------------
    # Lazy dependencies
    # ------------------------------------------------------------------
    def _client(self) -> httpx.AsyncClient:
        if self._http is not None:
            return self._http
        return httpx.AsyncClient(timeout=10.0)

    def _store(self) -> SecureStorage:
        if self._storage is None:
            self._storage = SecureStorage()
        return self._storage

    # ------------------------------------------------------------------
    # SMART discovery
    # ------------------------------------------------------------------
    async def discover(self) -> SMARTEndpoints:
        """Resolve the authorization/token endpoints via SMART discovery.

        Tries ``/.well-known/smart-configuration`` first; falls back to the
        sandbox's conventional ``/auth/authorize`` + ``/auth/token`` layout.
        """

        url = f"{self.fhir_base_url}/.well-known/smart-configuration"
        client = self._client()
        try:
            resp = await client.get(url, headers={"Accept": "application/json"})
            resp.raise_for_status()
            data = resp.json()
            return SMARTEndpoints(
                authorization_endpoint=data["authorization_endpoint"],
                token_endpoint=data["token_endpoint"],
            )
        except Exception as e:  # noqa: BLE001 - discovery is best-effort
            logger.warning("SMART discovery failed (%s); using sandbox defaults", e)
            base = self.fhir_base_url.rsplit("/fhir", 1)[0]
            return SMARTEndpoints(
                authorization_endpoint=f"{base}/auth/authorize",
                token_endpoint=f"{base}/auth/token",
            )

    # ------------------------------------------------------------------
    # Authorization URL
    # ------------------------------------------------------------------
    def authorization_url(
        self, endpoints: SMARTEndpoints, *, state: str, code_challenge: str, scope: str
    ) -> str:
        params = {
            "response_type": "code",
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "scope": scope,
            "state": state,
            "aud": self.fhir_base_url,
            "code_challenge": code_challenge,
            "code_challenge_method": "S256",
        }
        return f"{endpoints.authorization_endpoint}?{urlencode(params)}"

    async def exchange_code(
        self, endpoints: SMARTEndpoints, *, code: str, code_verifier: str
    ) -> Dict[str, Any]:
        """Exchange an authorization code for tokens at the token endpoint."""

        form = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self.redirect_uri,
            "client_id": self.client_id,
            "code_verifier": code_verifier,
        }
        # Confidential clients authenticate with the secret; public clients
        # rely on PKCE alone.
        if self.client_secret:
            form["client_secret"] = self.client_secret
        client = self._client()
        resp = await client.post(
            endpoints.token_endpoint,
            data=form,
            headers={"Accept": "application/json"},
        )
        resp.raise_for_status()
        return resp.json()

    async def fetch_patient_bundle(
        self, patient_id: str, *, access_token: str
    ) -> Dict[str, Any]:
        """Fetch a patient's record as an R4 Bundle via ``$everything``."""

        url = f"{self.fhir_base_url}/Patient/{patient_id}/$everything"
        client = self._client()
        resp = await client.get(
            url,
            headers={
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/fhir+json",
            },
        )
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # Persistence (ehr_integrations)
    # ------------------------------------------------------------------
    def _encrypt(self, data: Dict[str, Any]) -> bytes:
        return self._store().encrypt_blob(json.dumps(data))

    def _decrypt(self, blob: bytes) -> Dict[str, Any]:
        return json.loads(self._store().decrypt_blob(blob))

    async def begin_launch(self, db, *, tenant_id: uuid.UUID, scope: Optional[str] = None) -> str:
        """Create a pending integration and return the authorization URL."""

        scope = scope or DEFAULT_SCOPE
        endpoints = await self.discover()
        verifier, challenge = generate_pkce()
        # Prefix the state with the tenant UUID so the unauthenticated callback
        # can re-establish RLS context; the random suffix is the CSRF token.
        state = f"{tenant_id}.{_b64url_no_pad(secrets.token_bytes(24))}"

        row = EhrIntegration(
            tenant_id=tenant_id,
            ehr_vendor="smart-on-fhir",
            api_endpoint=self.fhir_base_url,
            status="pending_auth",
            auth_credentials_encrypted=self._encrypt(
                {
                    "state": state,
                    "code_verifier": verifier,
                    "token_endpoint": endpoints.token_endpoint,
                }
            ),
        )
        db.add(row)
        db.commit()
        return self.authorization_url(
            endpoints, state=state, code_challenge=challenge, scope=scope
        )

    async def complete_callback(self, db, *, code: str, state: str) -> EhrIntegration:
        """Resolve the pending row by ``state``, exchange the code, store tokens."""

        rows = (
            db.query(EhrIntegration)
            .filter(EhrIntegration.status == "pending_auth")
            .all()
        )
        row = None
        pending: Dict[str, Any] = {}
        for candidate in rows:
            try:
                data = self._decrypt(candidate.auth_credentials_encrypted)
            except Exception:  # noqa: BLE001 - skip undecryptable rows
                continue
            if secrets.compare_digest(str(data.get("state", "")), state):
                row, pending = candidate, data
                break
        if row is None:
            raise ValueError("No pending SMART launch matches the supplied state.")

        endpoints = SMARTEndpoints(
            authorization_endpoint="",
            token_endpoint=pending["token_endpoint"],
        )
        tokens = await self.exchange_code(
            endpoints, code=code, code_verifier=pending["code_verifier"]
        )
        row.auth_credentials_encrypted = self._encrypt(
            {
                "access_token": tokens.get("access_token"),
                "refresh_token": tokens.get("refresh_token"),
                "patient": tokens.get("patient"),
                "scope": tokens.get("scope"),
                "expires_in": tokens.get("expires_in"),
                "token_endpoint": pending["token_endpoint"],
            }
        )
        row.status = "active"
        db.commit()
        return row
