"""Migration smoke test — Task #1 regression guard.

Runs the real ``alembic upgrade head`` (plus a downgrade/upgrade round-trip)
against a throwaway database to catch the ORM/migration drift class of bug:
the one that made a fresh ``alembic upgrade head`` crash at the RLS migration
because ``tenant_api_keys`` and nine ``tenant_id`` columns were never created.

The test **skips cleanly** when no Postgres server is reachable, so
``pytest -q`` collection always succeeds on a machine without Docker running.
To exercise it, point at a Postgres+pgvector server:

    MIGRATION_SMOKE_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/postgres pytest -q

(or rely on the ``DATABASE_URL`` default the test conftest sets). The smoke
script creates and drops its own scratch database, so this never touches the
shared test database.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
SMOKE_SCRIPT = ROOT / "scripts" / "migrate_smoke.py"


def _admin_url() -> str | None:
    return os.getenv("MIGRATION_SMOKE_DATABASE_URL") or os.getenv("DATABASE_URL")


def _server_reachable(url: str) -> bool:
    """True if the Postgres *server* (maintenance DB) accepts a connection."""
    try:
        maint = make_url(url).set(database="postgres").render_as_string(hide_password=False)
        eng = create_engine(maint, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
        try:
            with eng.connect() as conn:
                conn.execute(text("SELECT 1"))
        finally:
            eng.dispose()
        return True
    except Exception:
        return False


@pytest.fixture(scope="module")
def reachable_admin_url() -> str:
    url = _admin_url()
    if not url:
        pytest.skip("no MIGRATION_SMOKE_DATABASE_URL / DATABASE_URL configured")
    if not _server_reachable(url):
        pytest.skip("Postgres server not reachable — skipping migration smoke")
    return url


def test_alembic_upgrade_head_on_fresh_db(reachable_admin_url: str) -> None:
    """A clean ``alembic upgrade head`` (+ reversibility) must succeed."""
    env = dict(os.environ)
    env["MIGRATION_SMOKE_DATABASE_URL"] = reachable_admin_url
    env.setdefault("BUDDI_TEST_MODE", "1")

    result = subprocess.run(
        [sys.executable, str(SMOKE_SCRIPT), "--roundtrip"],
        env=env,
        cwd=str(ROOT),
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, (
        "migrate_smoke.py failed (fresh `alembic upgrade head` is broken):\n"
        f"--- stdout ---\n{result.stdout}\n--- stderr ---\n{result.stderr}"
    )
    assert "invariants hold" in result.stdout
