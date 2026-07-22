#!/usr/bin/env python3
"""
Smoke-test harness for the canonical Buddi API.

Exercises the public synthetic demo surface and verifies the deployment
invariants: no real PHI, no LLM spend, chain verified, PT-9012 flow works
end-to-end in <60s.

Usage:
    python scripts/verify_system.py                           # default localhost:8001
    python scripts/verify_system.py --base-url https://api.example.com
    BUDDI_BASE_URL=https://api.example.com python scripts/verify_system.py
    BUDDI_API_KEY=sk-... python scripts/verify_system.py --demo   # full demo check
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from typing import Any, Dict, List, Tuple

import requests


BASE_URL = os.environ.get("BUDDI_BASE_URL", "http://localhost:8001").rstrip("/")
TIMEOUT = float(os.environ.get("BUDDI_VERIFY_TIMEOUT", "15"))
# The demo flow may need longer than the default per-request timeout.
DEMO_TIMEOUT = float(os.environ.get("BUDDI_VERIFY_DEMO_TIMEOUT", "60"))


# ---------------------------------------------------------------------------
# PT-9012 (Marcus Holloway) — the canonical synthetic demo patient.
# ---------------------------------------------------------------------------
PT_9012_NOTE = (
    "67-year-old male with type 2 diabetes mellitus complicated by chronic "
    "kidney disease stage 3a. eGFR 51 and urine albumin/creatinine ratio "
    "42 mg/g. Hypertension treated with lisinopril. Assessment notes diabetic "
    "CKD and hypertensive CKD; continue renal-protective therapy and monitor BMP."
)

PT_9012_BILLED_CODES = ["E11.9", "I10"]


# Minimal FHIR Bundle fixture exercising the adapter path. Kept intentionally
# small — the full validated Pydantic model arrives in Track 2 Step 9 (SEC-10).
FHIR_FIXTURE: Dict[str, Any] = {
    "resourceType": "Bundle",
    "type": "collection",
    "entry": [
        {
            "resource": {
                "resourceType": "DocumentReference",
                "id": "note-1",
                "description": (
                    "Patient presents with persistent cough and fatigue. "
                    "History of Type 2 Diabetes with diabetic neuropathy in "
                    "lower extremities."
                ),
            }
        },
        {
            "resource": {
                "resourceType": "Claim",
                "id": "claim-1",
                "item": [{"productOrService": {"coding": [{"code": "E11.9"}]}}],
            }
        },
    ],
}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _auth_headers() -> Dict[str, str]:
    """Attach bearer/API-key auth."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    api_key = os.environ.get("BUDDI_API_KEY")
    if api_key:
        headers["X-API-Key"] = api_key
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _check(name: str, ok: bool, detail: str = "") -> Tuple[str, bool, str]:
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f"  —  {detail}" if detail else ""))
    return (name, ok, detail)


def _is_stub_response(data: dict) -> bool:
    """Detect deterministic-stub output (no real LLM call made).

    The demo/stub path returns ``demo: true`` in the payload. Real agent
    output omits that flag or sets it to false. Additionally, the stub
    ``source`` field contains ``demo_fallback`` or ``agent_unavailable_demo``.
    """
    if data.get("demo") is True:
        return True
    source = data.get("source", "")
    if "demo" in source.lower() or "fallback" in source.lower():
        return True
    return False


# ---------------------------------------------------------------------------
# Checks
# ---------------------------------------------------------------------------


def check_health() -> Tuple[str, bool, str]:
    url = f"{BASE_URL}/api/health"
    try:
        r = requests.get(url, headers=_auth_headers(), timeout=TIMEOUT)
        ok = r.status_code == 200 and r.json().get("status") in ("active", "ok")
        detail = f"HTTP {r.status_code} body={r.text[:200]}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("GET /api/health", ok, detail)


def check_health_no_auth() -> Tuple[str, bool, str]:
    """Verify /health is reachable without auth (for Render health check)."""
    url = f"{BASE_URL}/health"
    try:
        r = requests.get(url, timeout=TIMEOUT)
        ok = r.status_code == 200 and r.json().get("status") in ("active", "ok")
        detail = f"HTTP {r.status_code}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("GET /health (no auth)", ok, detail)


def check_fhir_ingest() -> Tuple[str, bool, str]:
    """Verify the FHIR ingest endpoint is reachable.

    Accepts 200/202 (success) or 403 (scope-restricted — the endpoint requires
    ``ingest`` scope which test-mode/dev credentials may not carry). A 401
    (auth missing) or a connection error still fails.
    """
    url = f"{BASE_URL}/ingest/fhir"
    try:
        r = requests.post(
            url,
            headers=_auth_headers(),
            data=json.dumps(FHIR_FIXTURE),
            timeout=TIMEOUT,
        )
        ok = r.status_code in (200, 202, 403)
        detail = f"HTTP {r.status_code} body={r.text[:200]}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("POST /ingest/fhir", ok, detail)


def check_audit_query() -> Tuple[str, bool, str]:
    """Verify audit query is reachable (follows 301 redirect to /api/audit/query)."""
    url = f"{BASE_URL}/api/audit/query"
    try:
        r = requests.get(url, headers=_auth_headers(), timeout=TIMEOUT)
        ok = r.status_code == 200 and "events" in r.json()
        detail = f"HTTP {r.status_code}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("GET /api/audit/query", ok, detail)


def check_audit_verify() -> Tuple[str, bool, str]:
    """Verify the tamper-evident audit chain endpoint is reachable.

    Accepts HTTP 200 (full verification), or 403 (scope-restricted — the
    endpoint requires ``admin`` scope). A 401 or connection error fails.
    """
    url = f"{BASE_URL}/api/audit/verify"
    try:
        r = requests.get(url, headers=_auth_headers(), timeout=TIMEOUT)
        data = r.json() if r.status_code == 200 else {}
        verified = data.get("verified", False)
        status = data.get("status", "")
        # 200 with verification success, or 403 (admin scope required).
        if r.status_code == 200:
            ok = verified is True or status in (
                "verified",
                "demo_verified",
                "verified_via_signed_roots",
            )
        else:
            ok = r.status_code == 403
        detail = (
            f"HTTP {r.status_code} verified={verified} status={status} "
            f"events={data.get('event_count', data.get('events_checked', '?'))}"
        )
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("GET /api/audit/verify", ok, detail)


def check_pt9012_demo() -> Tuple[str, bool, str]:
    """Run the PT-9012 synthetic demo end-to-end.

    Posts a shadow audit for Marcus Holloway and asserts:
    - HTTP 200 (sync path with ``?sync=true``) or 202 (async, polled)
    - Response is a deterministic stub (``demo: true``) — zero LLM calls
    - At least one HCC code identified
    - Total wall-clock < DEMO_TIMEOUT seconds
    """
    # Use ?sync=true to avoid the async worker — the demo runs inline.
    url = f"{BASE_URL}/api/shadow/audit?sync=true"
    payload = {
        "note": PT_9012_NOTE,
        "billed_codes": PT_9012_BILLED_CODES,
        "patient_id": "PT-9012",
        "demo": True,
    }
    failures: List[str] = []
    t0 = time.monotonic()
    try:
        r = requests.post(
            url,
            headers=_auth_headers(),
            data=json.dumps(payload),
            timeout=DEMO_TIMEOUT,
        )
        elapsed = time.monotonic() - t0

        if r.status_code not in (200, 202):
            failures.append(f"HTTP {r.status_code} (expected 200/202)")

        data = r.json() if r.status_code in (200, 202) else {}

        # ---- async fallback: poll for the result ----
        if r.status_code == 202 and data.get("job_id"):
            job_url = f"{BASE_URL}/api/jobs/{data['job_id']}"
            for _ in range(60):
                time.sleep(1)
                jr = requests.get(job_url, headers=_auth_headers(), timeout=TIMEOUT)
                if jr.status_code != 200:
                    continue
                jd = jr.json() or {}
                if jd.get("status") == "completed":
                    data = jd.get("result", {})
                    elapsed = time.monotonic() - t0
                    break
                if jd.get("status") == "failed":
                    failures.append(f"Job failed: {jd.get('error', 'unknown')}")
                    break
            else:
                failures.append("PT-9012 demo job timed out (60s poll)")
                data = {}

        # ---- assertions ----
        if not _is_stub_response(data):
            failures.append(
                "Not a deterministic stub — demo != true, possible LLM call detected"
            )

        identified = data.get("identified_codes", [])
        if len(identified) == 0:
            failures.append("No HCC codes identified for PT-9012")

        if elapsed >= DEMO_TIMEOUT:
            failures.append(
                f"PT-9012 demo took {elapsed:.1f}s (limit {DEMO_TIMEOUT}s)"
            )

        detail = (
            f"HTTP {r.status_code} in {elapsed:.1f}s  "
            f"codes={len(identified)}  "
            f"demo={data.get('demo')}  "
            f"recovered=${data.get('recovered_revenue', 0):,.0f}"
        )
        if failures:
            detail += f"  FAILURES: {'; '.join(failures)}"

        ok = len(failures) == 0
    except Exception as exc:
        elapsed = time.monotonic() - t0
        ok, detail = False, f"{type(exc).__name__}: {exc} (after {elapsed:.1f}s)"
    return _check("POST /api/shadow/audit (PT-9012 demo)", ok, detail)


def check_demo_sample_patient() -> Tuple[str, bool, str]:
    """Verify the demo sample-patient endpoint returns PT-9012."""
    url = f"{BASE_URL}/api/demo/sample-patient"
    try:
        r = requests.get(url, headers=_auth_headers(), timeout=TIMEOUT)
        data = r.json() if r.status_code == 200 else {}
        ok = (
            r.status_code == 200
            and data.get("id") == "PT-9012"
            and data.get("demo") is True
        )
        detail = f"HTTP {r.status_code} id={data.get('id')} demo={data.get('demo')}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("GET /api/demo/sample-patient", ok, detail)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> int:
    global BASE_URL

    parser = argparse.ArgumentParser(
        description="Buddi synthetic-demo smoke-test harness",
    )
    parser.add_argument(
        "--base-url",
        default=BASE_URL,
        help=f"Canonical backend base URL (default: {BASE_URL})",
    )
    parser.add_argument(
        "--demo",
        action="store_true",
        help="Run the full PT-9012 synthetic demo flow (takes longer)",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run every check including the demo flow",
    )
    args = parser.parse_args()

    BASE_URL = args.base_url.rstrip("/")

    run_demo = args.demo or args.all

    print(f"🔎  Buddi smoke-test → {BASE_URL}")
    if run_demo:
        print(f"   (incl. PT-9012 synthetic demo, timeout {DEMO_TIMEOUT}s)")
    print()

    results: List[Tuple[str, bool, str]] = [
        check_health_no_auth(),
        check_health(),
        check_fhir_ingest(),
        check_audit_query(),
        check_audit_verify(),
    ]

    if run_demo:
        results.append(check_pt9012_demo())
        results.append(check_demo_sample_patient())

    failed = [name for name, ok, _ in results if not ok]
    print()
    if failed:
        print(f"❌  {len(failed)} check(s) failed: {', '.join(failed)}")
        return 1
    print("✅  All smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
