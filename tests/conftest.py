"""Pytest fixtures for Buddi integration tests.

Sets the environment variables the production config expects *before* any
application module is imported, so the pydantic-settings validation passes
and we do not accidentally pick up a developer's real credentials.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

# Guarantee the repo root is on sys.path when pytest is run from anywhere.
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---- Test-mode secrets -----------------------------------------------------
# BUDDI_TEST_MODE lets core/config auto-fill the mandatory security fields
# with test-only defaults. These are never used in production.
os.environ.setdefault("BUDDI_TEST_MODE", "1")
os.environ.setdefault("ENVIRONMENT", "test")
os.environ.setdefault(
    "SECRET_KEY",
    "test-only-secret-key-not-for-production-use-0123456789abcdef",
)
os.environ.setdefault("BUDDI_STORAGE_KEY", "test-only-storage-key-not-for-prod")
os.environ.setdefault("API_KEY", "test-api-key-abcdef1234567890")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

# CMS-AUD-01: keep the daily Merkle-root background task disabled during
# unit tests. The seal pipeline is exercised explicitly in test_audit_merkle.py
# and via /api/audit/roots/seal so we don't need a 24h asyncio loop running
# in the TestClient lifespan, which would otherwise try to query a possibly
# offline DB at startup.
os.environ.setdefault("BUDDI_DISABLE_MERKLE_TASK", "1")
# Point the signed-roots export at a per-run temp dir so tests don't write
# into the developer's checked-in storage/audit_roots/.
import tempfile  # noqa: E402
os.environ.setdefault(
    "BUDDI_AUDIT_ROOTS_DIR",
    os.path.join(tempfile.gettempdir(), "buddi-test-audit-roots"),
)


# Point the app at the test Postgres spun up by the developer / CI.
# If the test DB is unreachable, the DB-backed endpoints will return
# their "soft-fail" payloads and the tests assert on the HTTP layer only.
os.environ.setdefault(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5433/buddi",
)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402


@pytest.fixture(scope="session")
def api_key() -> str:
    return os.environ["API_KEY"]


@pytest.fixture(scope="session")
def client(api_key):
    """FastAPI TestClient with the lifespan (Agent bootstrap) active."""
    from backend.api import app

    with TestClient(app) as tc:
        yield tc


@pytest.fixture(scope="session")
def auth_headers(api_key):
    """Default headers for authenticated requests."""
    return {"Authorization": f"Bearer {api_key}"}
