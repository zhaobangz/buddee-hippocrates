#!/usr/bin/env python3
"""
Smoke-test harness for the canonical Buddi API.

Track 1 / Step 1 (TEST-04 partial, ARCH-01): points at the canonical surface
(`backend.api:app` on port 8001) and exercises the three endpoints the audit
called out: ``GET /api/health``, ``POST /ingest/fhir``, ``GET /audit/query``.

This is intentionally a thin script — it is NOT a substitute for the pytest
suite that lands in Track 3 Step 16. It returns a non-zero exit code if any
check fails so it can be used as a post-deploy smoke step in CI.

Usage:
    python scripts/verify_system.py                  # default localhost:8001
    BUDDI_BASE_URL=https://api.example.com python scripts/verify_system.py
"""
from __future__ import annotations

import json
import os
import sys
from typing import Any, Dict, List, Tuple

import requests


BASE_URL = os.environ.get("BUDDI_BASE_URL", "http://localhost:8001").rstrip("/")
TIMEOUT = float(os.environ.get("BUDDI_VERIFY_TIMEOUT", "15"))


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


def _auth_headers() -> Dict[str, str]:
    """Attach bearer/API-key auth once Track 1 Step 3 lands (SEC-02)."""
    headers: Dict[str, str] = {"Content-Type": "application/json"}
    api_key = os.environ.get("BUDDI_API_KEY")
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    return headers


def _check(name: str, ok: bool, detail: str = "") -> Tuple[str, bool, str]:
    mark = "✅" if ok else "❌"
    print(f"  {mark} {name}" + (f"  —  {detail}" if detail else ""))
    return (name, ok, detail)


def check_health() -> Tuple[str, bool, str]:
    url = f"{BASE_URL}/api/health"
    try:
        r = requests.get(url, headers=_auth_headers(), timeout=TIMEOUT)
        ok = r.status_code == 200 and r.json().get("status") == "active"
        detail = f"HTTP {r.status_code} body={r.text[:200]}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("GET /api/health", ok, detail)


def check_fhir_ingest() -> Tuple[str, bool, str]:
    url = f"{BASE_URL}/ingest/fhir"
    try:
        r = requests.post(
            url,
            headers=_auth_headers(),
            data=json.dumps(FHIR_FIXTURE),
            timeout=TIMEOUT,
        )
        ok = r.status_code in (200, 202)
        detail = f"HTTP {r.status_code} body={r.text[:200]}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("POST /ingest/fhir", ok, detail)


def check_audit_query() -> Tuple[str, bool, str]:
    url = f"{BASE_URL}/audit/query"
    try:
        r = requests.get(url, headers=_auth_headers(), timeout=TIMEOUT)
        ok = r.status_code == 200 and "events" in r.json()
        detail = f"HTTP {r.status_code}"
    except Exception as exc:
        ok, detail = False, f"{type(exc).__name__}: {exc}"
    return _check("GET /audit/query", ok, detail)


def main() -> int:
    print(f"🔎  Buddi smoke-test → {BASE_URL}")
    results: List[Tuple[str, bool, str]] = [
        check_health(),
        check_fhir_ingest(),
        check_audit_query(),
    ]
    failed = [name for name, ok, _ in results if not ok]
    print()
    if failed:
        print(f"❌  {len(failed)} check(s) failed: {', '.join(failed)}")
        return 1
    print("✅  All smoke checks passed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
