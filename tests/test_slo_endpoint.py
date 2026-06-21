"""Tests for the PROMPT_07 GET /api/metrics/slo endpoint.

Scope/auth checks run without a DB; the data-shape and PHI-safety checks need a
real tenant + Postgres (via the ``tenant_api_key`` fixture) and skip cleanly
when no test DB is present.
"""

from __future__ import annotations

import json

from core.safety import redact_pii

_REQUIRED_KEYS = {
    "shadow_audit_p95_ms",
    "prior_auth_p95_ms",
    "audit_chain_verify_ok",
    "audit_chain_last_verified_at",
    "suggestions_approved_7d",
    "suggestions_rejected_7d",
    "suggestions_abstained_7d",
    "suggestion_approval_rate_7d",
    "encounters_processed_24h",
    "generated_at",
    "tenant_id_hash",
}


def test_slo_requires_admin_scope(client, auth_headers):
    # Test-mode key carries only ["test", "clinician"] — not admin -> 403.
    resp = client.get("/api/metrics/slo", headers=auth_headers)
    assert resp.status_code == 403


def test_slo_returns_expected_keys(client, tenant_api_key):
    headers = tenant_api_key(["admin"])
    resp = client.get("/api/metrics/slo", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert _REQUIRED_KEYS.issubset(body.keys())


def test_slo_phi_safe(client, tenant_api_key):
    headers = tenant_api_key(["admin"])
    resp = client.get("/api/metrics/slo", headers=headers)
    assert resp.status_code == 200
    raw = json.dumps(resp.json())
    # No SSN / email / MRN / DOB pattern should survive redaction unchanged.
    assert redact_pii(raw) == raw


def test_slo_no_data(client, tenant_api_key):
    # A fresh tenant has no jobs/suggestions: numeric latency fields are null,
    # counts are 0, and the call succeeds (no error).
    headers = tenant_api_key(["admin"])
    resp = client.get("/api/metrics/slo", headers=headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["shadow_audit_p95_ms"] is None
    assert body["prior_auth_p95_ms"] is None
    assert body["suggestions_approved_7d"] == 0
    assert body["encounters_processed_24h"] == 0
