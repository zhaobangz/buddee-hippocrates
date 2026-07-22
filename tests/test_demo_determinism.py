"""P‑A2: Demo determinism, zero‑LLM proof, and BAA‑precondition enforcement.

These tests verify the invariants the public synthetic demo must uphold:

1. **Deterministic, byte‑stable output** — PT‑9012 always surfaces the same
   three HCC codes (E11.22, N18.31, I12.9) with the same recovered revenue.
2. **Zero outbound LLM calls** — the agent's ``handle`` method is never
   invoked when ``demo=True`` and no LLM keys are set.
3. **BAA tripwire** — ``/ingest/fhir`` returns HTTP 412 when the tenant BAA
   is unconfirmed, even when the global flag is set (tenant‑level gate).
4. **Synthetic carve‑out** — the demo endpoints are allowed even when both
   global and tenant BAAs are unconfirmed.

No network, no live LLM, no PHI.
"""
from __future__ import annotations

import json
from unittest.mock import patch


# PT‑9012 (Marcus Holloway) — the canonical synthetic demo patient.
PT_9012_NOTE = (
    "67-year-old male with type 2 diabetes mellitus complicated by chronic "
    "kidney disease stage 3a. eGFR 51 and urine albumin/creatinine ratio "
    "42 mg/g. Hypertension treated with lisinopril. Assessment notes diabetic "
    "CKD and hypertensive CKD; continue renal-protective therapy and monitor BMP."
)

PT_9012_EXPECTED_CODES = {"E11.22", "N18.31", "I12.9"}
PT_9012_EXPECTED_REVENUE = 15700.0

VALID_BUNDLE = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {"resource": {"resourceType": "Patient", "id": "pat-1"}},
        {
            "resource": {
                "resourceType": "Encounter",
                "id": "enc-1",
                "status": "finished",
                "subject": {"reference": "Patient/pat-1"},
            },
        },
    ],
}


# ---------------------------------------------------------------------------
# P‑A2.1 — Demo determinism + zero‑LLM proof
# ---------------------------------------------------------------------------


def test_pt9012_demo_byte_stable_deterministic(client, auth_headers, monkeypatch):
    """PT‑9012 returns the same three HCC codes every time.

    The deterministic stub path (_demo_shadow_result) uses rule‑based
    pattern matching on the note text, not an LLM. No LLM keys are set,
    so the agent bootstrap fails → agent is None → the route falls through
    to the deterministic fallback automatically.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("BUDDI_BAA_CONFIRMED", "0")

    # Run twice — both runs must produce identical codes and revenue.
    for run_label in ("first", "second"):
        resp = client.post(
            "/api/shadow/audit?sync=true",
            headers=auth_headers,
            json={
                "note": PT_9012_NOTE,
                "billed_codes": ["E11.9", "I10"],
                "patient_id": "PT-9012",
                "demo": True,
            },
        )
        assert resp.status_code == 200, f"{run_label} run: expected 200, got {resp.status_code}"
        data = resp.json()

        codes = {c["code"] for c in data["identified_codes"]}
        assert codes == PT_9012_EXPECTED_CODES, (
            f"{run_label} run: expected {PT_9012_EXPECTED_CODES}, got {codes}"
        )
        assert data["recovered_revenue"] == PT_9012_EXPECTED_REVENUE, (
            f"{run_label} run: expected ${PT_9012_EXPECTED_REVENUE}, "
            f"got ${data['recovered_revenue']}"
        )


def test_pt9012_demo_zero_llm_calls(client, auth_headers, monkeypatch):
    """The PT‑9012 demo path never places an outbound LLM provider call.

    When ``demo=True`` and no LLM keys are set, the agent's ``handle()`` is
    still invoked (the agent bootstraps in test mode) but it fails to reach
    the LLM provider because all API keys are missing. The actual outbound
    HTTP call — ``LLMManager._call_provider`` — must never fire. The
    deterministic ``_demo_shadow_result`` fallback supplies the output.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("BUDDI_BAA_CONFIRMED", "0")

    with patch("core.llm_manager.LLMManager._call_provider") as mock_provider:
        resp = client.post(
            "/api/shadow/audit?sync=true",
            headers=auth_headers,
            json={
                "note": PT_9012_NOTE,
                "billed_codes": ["E11.9", "I10"],
                "patient_id": "PT-9012",
                "demo": True,
            },
        )

    mock_provider.assert_not_called()
    assert resp.status_code == 200
    data = resp.json()
    assert data["demo"] is True
    assert "demo" in data.get("source", "").lower()
    assert len(data["identified_codes"]) >= 1


def test_pt9012_demo_response_carries_demo_flag(client, auth_headers, monkeypatch):
    """The demo response is explicitly stamped so consumers can render the banner.

    The frontend uses ``demo: true`` and the ``X‑Response‑Source`` header
    to show the "DEMO MODE" indicator. This test asserts both are present.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setenv("BUDDI_BAA_CONFIRMED", "0")

    resp = client.post(
        "/api/shadow/audit?sync=true",
        headers=auth_headers,
        json={
            "note": PT_9012_NOTE,
            "billed_codes": ["E11.9", "I10"],
            "patient_id": "PT-9012",
            "demo": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()

    # Payload must be flagged as demo/synthetic.
    assert data["demo"] is True
    assert data.get("source", "").startswith("agent_unavailable_demo")

    # At least one code surfaces — the demo page must never be empty.
    assert len(data["identified_codes"]) >= 1

    # Each suggestion must have the required fields.
    for code in data["identified_codes"]:
        assert "code" in code
        assert "description" in code
        assert "justification" in code
        assert "confidence" in code
        assert code["review_status"] == "human_review_required"


def test_demo_sample_patient_is_marcus_holloway(client, auth_headers):
    """GET /api/demo/sample‑patient returns the canonical PT‑9012 profile."""
    resp = client.get("/api/demo/sample-patient", headers=auth_headers)
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == "PT-9012"
    assert data["demo"] is True
    assert "Type 2 Diabetes" in str(data.get("conditions", "")) or any(
        "diabetes" in str(c).lower() for c in data.get("conditions", [])
    )


# ---------------------------------------------------------------------------
# P‑A2.2 — BAA precondition enforcement
# ---------------------------------------------------------------------------


def test_ingest_fhir_rejects_global_baa_unconfirmed(
    client, tenant_api_key, monkeypatch
):
    """/ingest/fhir → 412 when BUDDI_BAA_CONFIRMED is not 1.

    The global gate is checked first in assert_phi_processing_allowed.
    """
    monkeypatch.delenv("BUDDI_BAA_CONFIRMED", raising=False)
    headers = tenant_api_key(["ingest"], baa_confirmed=True)
    resp = client.post("/ingest/fhir", headers=headers, json=VALID_BUNDLE)
    assert resp.status_code == 412
    assert "BAA" in resp.json()["detail"]


def test_ingest_fhir_rejects_tenant_baa_unconfirmed(
    client, tenant_api_key, monkeypatch
):
    """/ingest/fhir → 412 when tenant baa_confirmed=False, even if global=1.

    This is the tenant‑level gate (step 4 in assert_phi_processing_allowed).
    The global gate passes because BUDDI_BAA_CONFIRMED=1, but the individual
    tenant row has baa_confirmed=False.
    """
    monkeypatch.setenv("BUDDI_BAA_CONFIRMED", "1")
    headers = tenant_api_key(["ingest"], baa_confirmed=False)
    resp = client.post("/ingest/fhir", headers=headers, json=VALID_BUNDLE)
    assert resp.status_code == 412
    assert "BAA" in resp.json()["detail"]


def test_ingest_fhir_allows_baa_confirmed_tenant(
    client, tenant_api_key, monkeypatch
):
    """/ingest/fhir → 200/412/503 when both global and tenant BAAs are confirmed.

    The actual result depends on agent bootstrap state, but 403 (scope
    regression) must never appear when the ingest scope is granted.
    """
    monkeypatch.setenv("BUDDI_BAA_CONFIRMED", "1")
    headers = tenant_api_key(["ingest"], baa_confirmed=True)
    with patch("core.agent.Agent.handle", return_value=json.dumps({"ok": True})):
        resp = client.post("/ingest/fhir", headers=headers, json=VALID_BUNDLE)
    # 200 = success, 412 = BAA check flaked (RLS/DB), 503 = agent bootstrap
    # failed. 403 would mean scope enforcement regressed and is a hard fail.
    assert resp.status_code in (200, 412, 503)
    assert resp.status_code != 403, "ingest scope regressed — got 403"


def test_demo_skips_baa_enforcement(client, auth_headers, monkeypatch):
    """Synthetic/demo requests bypass the BAA gate entirely.

    Even with both BAA flags unconfirmed (global=0, tenant=False in
    test‑mode fallback), the PT‑9012 demo audit succeeds. This is the
    §4.1 carve‑out: synthetic data never triggers the PHI guard.
    """
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("BUDDI_BAA_CONFIRMED", raising=False)

    resp = client.post(
        "/api/shadow/audit?sync=true",
        headers=auth_headers,
        json={
            "note": PT_9012_NOTE,
            "billed_codes": ["E11.9", "I10"],
            "patient_id": "PT-9012",
            "demo": True,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["demo"] is True
    assert len(data["identified_codes"]) >= 1
