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
# Disable the per-IP/per-key rate limiter for the suite. CI sets this in the
# workflow env and evals/run_eval.py sets it via setdefault; without it a bare
# local ``pytest -q`` accumulates enough requests across the session to trip
# the limiter and return 429 from later tests (order-dependent flakiness).
# Rate limiting remains fully active in production — this only affects tests.
os.environ.setdefault("BUDDI_RATE_LIMIT_DISABLED", "1")
# Build-out B3: don't spin the async job worker in the test lifespan — there is
# no DB to poll, and tests exercise the queue via ?sync=true + unit tests.
os.environ.setdefault("BUDDI_DISABLE_JOB_WORKER", "1")
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
    """Default headers for authenticated requests.

    Resolves to the test-mode static fallback identity, which (after the Issue 6
    hardening) carries only the ``["test", "clinician"]`` scopes. Use the
    ``tenant_api_key`` fixture for routes that require ``ingest`` or ``admin``.
    """
    return {"Authorization": f"Bearer {api_key}"}


@pytest.fixture
def tenant_api_key():
    """Provision a real per-tenant API key with explicit scopes.

    Issue 6 reduced the test-mode static fallback to ``["test", "clinician"]``,
    so tests that exercise ``ingest``/``admin`` routes can no longer borrow those
    scopes from the fallback. This fixture inserts a real ``Tenant`` +
    ``TenantApiKey`` row (the key is verified through the normal
    ``require_api_client`` DB lookup path) and returns auth headers for it.

    It **skips the test** when the test Postgres is unreachable — that is the
    default locally; CI provisions Postgres on :5433 and runs migrations first.

    Yields a callable: ``make(scopes, *, baa_confirmed=False) -> headers``.
    """
    import uuid as _uuid

    from backend.auth import api_key_lookup_hash, hash_api_key
    from core import models
    from core.database import SessionLocal

    created = []

    def _make(scopes, *, baa_confirmed=False):
        raw_key = f"test-real-key-{_uuid.uuid4().hex}"
        db = SessionLocal()
        try:
            tenant = models.Tenant(
                name=f"test-tenant-{_uuid.uuid4().hex[:8]}",
                baa_confirmed=baa_confirmed,
            )
            db.add(tenant)
            db.flush()
            key = models.TenantApiKey(
                tenant_id=tenant.id,
                key_hash_sha256=api_key_lookup_hash(raw_key),
                hashed_key=hash_api_key(raw_key),
                scopes=list(scopes),
            )
            db.add(key)
            db.commit()
            created.append((tenant.id, key.id))
        except Exception as exc:  # noqa: BLE001 - any DB failure => skip, not fail
            db.rollback()
            pytest.skip(f"test Postgres unavailable; real TenantApiKey required: {exc}")
        finally:
            db.close()
        return {"Authorization": f"Bearer {raw_key}"}

    yield _make

    if created:
        db = SessionLocal()
        try:
            for tenant_id, key_id in created:
                db.query(models.TenantApiKey).filter(models.TenantApiKey.id == key_id).delete()
                db.query(models.Tenant).filter(models.Tenant.id == tenant_id).delete()
            db.commit()
        except Exception:  # noqa: BLE001 - best-effort cleanup
            db.rollback()
        finally:
            db.close()
