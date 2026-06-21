"""Tests for the build-out B1 SMART-on-FHIR launcher.

The pure protocol surface (PKCE, discovery, authorization URL, code exchange,
patient fetch) is exercised against a mocked SMART authorization server via
``httpx.MockTransport`` — no network, no DB, no real EHR. The DB-backed
begin_launch/complete_callback round trip needs Postgres and is covered by the
integration suite (skips without a test DB).
"""

from __future__ import annotations

import base64
import hashlib
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from backend.smart_fhir import (
    SMARTEndpoints,
    SMARTFHIRLauncher,
    generate_pkce,
    tenant_id_from_state,
)

SANDBOX = "https://launch.smarthealthit.org/v/r4/fhir"
AUTHZ = "https://launch.smarthealthit.org/v/r4/auth/authorize"
TOKEN = "https://launch.smarthealthit.org/v/r4/auth/token"


def _mock_smart_server() -> httpx.MockTransport:
    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path.endswith("/.well-known/smart-configuration"):
            return httpx.Response(
                200,
                json={
                    "authorization_endpoint": AUTHZ,
                    "token_endpoint": TOKEN,
                },
            )
        if path.endswith("/auth/token"):
            return httpx.Response(
                200,
                json={
                    "access_token": "ACCESS_123",
                    "refresh_token": "REFRESH_456",
                    "patient": "smart-1288992",
                    "scope": "patient/*.read",
                    "expires_in": 3600,
                },
            )
        if "/Patient/" in path and path.endswith("/$everything"):
            return httpx.Response(
                200,
                json={"resourceType": "Bundle", "type": "searchset", "entry": []},
            )
        return httpx.Response(404, json={"error": "not found"})

    return httpx.MockTransport(handler)


def _launcher() -> SMARTFHIRLauncher:
    return SMARTFHIRLauncher(
        client_id="buddi-test",
        client_secret="",
        redirect_uri="http://localhost:8001/api/ehr/callback",
        fhir_base_url=SANDBOX,
        http_client=httpx.AsyncClient(transport=_mock_smart_server()),
    )


def test_generate_pkce_is_valid_s256():
    verifier, challenge = generate_pkce()
    expected = base64.urlsafe_b64encode(
        hashlib.sha256(verifier.encode()).digest()
    ).rstrip(b"=").decode()
    assert challenge == expected
    assert "=" not in challenge  # base64url, no padding


def test_tenant_id_from_state_roundtrip():
    assert str(tenant_id_from_state("11111111-1111-1111-1111-111111111111.xyz")) == (
        "11111111-1111-1111-1111-111111111111"
    )
    assert tenant_id_from_state("not-a-uuid.xyz") is None
    assert tenant_id_from_state("") is None


@pytest.mark.asyncio
async def test_discover_reads_well_known():
    endpoints = await _launcher().discover()
    assert endpoints.authorization_endpoint == AUTHZ
    assert endpoints.token_endpoint == TOKEN


def test_authorization_url_contains_pkce_and_aud():
    launcher = _launcher()
    endpoints = SMARTEndpoints(authorization_endpoint=AUTHZ, token_endpoint=TOKEN)
    url = launcher.authorization_url(
        endpoints, state="tid.rand", code_challenge="CHALLENGE", scope="patient/*.read"
    )
    qs = parse_qs(urlparse(url).query)
    assert qs["response_type"] == ["code"]
    assert qs["code_challenge"] == ["CHALLENGE"]
    assert qs["code_challenge_method"] == ["S256"]
    assert qs["aud"] == [SANDBOX]
    assert qs["state"] == ["tid.rand"]
    assert qs["client_id"] == ["buddi-test"]


@pytest.mark.asyncio
async def test_exchange_code_returns_tokens():
    launcher = _launcher()
    endpoints = SMARTEndpoints(authorization_endpoint=AUTHZ, token_endpoint=TOKEN)
    tokens = await launcher.exchange_code(endpoints, code="abc", code_verifier="v")
    assert tokens["access_token"] == "ACCESS_123"
    assert tokens["refresh_token"] == "REFRESH_456"
    assert tokens["patient"] == "smart-1288992"


@pytest.mark.asyncio
async def test_fetch_patient_bundle():
    bundle = await _launcher().fetch_patient_bundle("smart-1288992", access_token="ACCESS_123")
    assert bundle["resourceType"] == "Bundle"
