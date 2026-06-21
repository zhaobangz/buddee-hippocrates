"""Tests for the build-out A3 hosted-demo fixtures.

Covers:
  * The committed 5-bundle fixture set under evals/synthea/fixtures/.
  * _fixture_note() / bundle_name sourcing in _demo_shadow_result (A3.4),
    including backward compat (an explicit note always wins).
  * The clinician-scoped /api/demo/bundles routes (A3.3), which must serve
    without the Anthropic key or BAA tripwire.

No network, no live LLM, no PHI (fixtures are Safe-Harbor synthetic).
"""

from __future__ import annotations

from backend.api import (
    _demo_fixture_path,
    _demo_shadow_result,
    _fixture_note,
)


# ---------------------------------------------------------------------------
# Fixture-note sourcing
# ---------------------------------------------------------------------------


def test_fixture_note_marcus_holloway_is_diabetic_ckd():
    note = _fixture_note("marcus_holloway")
    assert "diabetes" in note.lower()
    assert "kidney" in note.lower()


def test_fixture_note_missing_returns_empty():
    assert _fixture_note("no_such_patient") == ""


def test_fixture_path_rejects_traversal():
    assert _demo_fixture_path("../../etc/passwd") is None
    assert _demo_fixture_path("..") is None


def test_demo_shadow_result_sources_note_from_default_bundle():
    # No note supplied → the marcus_holloway fixture (diabetic CKD) drives it.
    result = _demo_shadow_result(patient_id="demo", note="")
    assert result["bundle_name"] == "marcus_holloway"
    surfaced = {c["code"] for c in result["identified_codes"]}
    assert "E11.22" in surfaced


def test_demo_shadow_result_explicit_note_wins_backward_compat():
    # An explicit note must override the fixture (eval harness / live route).
    explicit = "Patient with morbid obesity, BMI 45. Weight management counseling."
    result = _demo_shadow_result(
        patient_id="demo",
        note=explicit,
        bundle_name="marcus_holloway",
        include_fallback=False,
    )
    surfaced = {c["code"] for c in result["identified_codes"]}
    # The diabetic-CKD rules must NOT fire on the obesity note.
    assert "E11.22" not in surfaced
    assert surfaced == set()


# ---------------------------------------------------------------------------
# /api/demo/bundles routes
# ---------------------------------------------------------------------------


def test_list_demo_bundles_returns_five_fixtures(client, auth_headers):
    resp = client.get("/api/demo/bundles", headers=auth_headers)
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 5
    assert body["synthetic"] is True
    names = {b["name"] for b in body["bundles"]}
    assert "marcus_holloway.json" in names


def test_fetch_demo_bundle_returns_fhir_bundle(client, auth_headers):
    resp = client.get("/api/demo/bundles/marcus_holloway.json", headers=auth_headers)
    assert resp.status_code == 200
    bundle = resp.json()
    assert bundle["resourceType"] == "Bundle"


def test_fetch_demo_bundle_unknown_is_404(client, auth_headers):
    resp = client.get("/api/demo/bundles/nope.json", headers=auth_headers)
    assert resp.status_code == 404


def test_list_demo_bundles_requires_auth(client):
    resp = client.get("/api/demo/bundles")
    assert resp.status_code == 401
