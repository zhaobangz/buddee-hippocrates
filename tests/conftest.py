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
os.environ.setdefault(
    "SECRET_KEY",
    "test-only-secret-key-not-for-production-use-0123456789abcdef",
)
os.environ.setdefault("BUDDI_STORAGE_KEY", "test-only-storage-key-not-for-prod")
os.environ.setdefault("API_KEY", "test-api-key-abcdef1234567890")
os.environ.setdefault("CORS_ORIGINS", "http://localhost:5173")

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
