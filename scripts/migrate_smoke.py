#!/usr/bin/env python3
"""Migration smoke test — prove ``alembic upgrade head`` works on a *fresh* DB.

This is the guard for the ORM/migration drift class of bug (the kind that
made a clean ``alembic upgrade head`` crash at the RLS migration). It:

  1. connects to a Postgres *server* using an admin URL,
  2. creates a brand-new throwaway database (``CREATE DATABASE``),
  3. runs ``alembic upgrade head`` against it (the real operator command,
     invoked as a subprocess so this script never imports the app),
  4. asserts a few schema invariants that regress the historical drift
     (``tenant_api_keys`` exists; every tenant-scoped table has
     ``tenant_id``; ``audit_events`` is partitioned),
  5. optionally round-trips ``downgrade base`` + ``upgrade head`` to prove
     reversibility (``--roundtrip``),
  6. drops the throwaway database — even on failure.

The database must have the ``pgvector`` extension *available* to install
(the ``pgvector/pgvector`` image or ``CREATE EXTENSION vector`` privileges);
the initial migration runs ``CREATE EXTENSION IF NOT EXISTS vector``.

Usage
-----
    # Point at a reachable Postgres+pgvector server. The DB named in the URL
    # is the *template/admin* connection target; the scratch DB is derived
    # from it and created/dropped automatically.
    MIGRATION_SMOKE_DATABASE_URL=postgresql://postgres:postgres@localhost:5433/postgres \\
        python scripts/migrate_smoke.py --roundtrip

    # Falls back to DATABASE_URL if MIGRATION_SMOKE_DATABASE_URL is unset.
    DATABASE_URL=postgresql://postgres:postgres@localhost:5433/buddi \\
        python scripts/migrate_smoke.py

Exit codes:
    0 — upgrade head (and round-trip, if requested) succeeded; invariants held
    1 — a migration failed, an invariant did not hold, or no DB was reachable
    2 — bad invocation (no usable database URL)
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_INI = ROOT / "alembic.ini"

# Tenant-scoped tables that MUST carry a tenant_id after upgrade head. This is
# the exact set the historical drift left without one (see migration
# b1f2c3d4e5a6) plus the always-present ones — kept here as the regression
# contract for the smoke test.
_TENANT_ID_TABLES = (
    "tenant_api_keys",
    "patients",
    "encounters",
    "billing_codes",
    "clinical_notes",
    "hcc_suggestions",
    "prior_authorization_requests",
    "prior_auth_states",
    "llm_requests",
    "llm_responses",
    "rag_retrievals",
    "document_chunks",
    "ehr_integrations",
    "compliance_flags",
    "audit_events",
    "recovery_events",
)


def _resolve_admin_url() -> str | None:
    url = os.getenv("MIGRATION_SMOKE_DATABASE_URL") or os.getenv("DATABASE_URL")
    return url.strip() if url else None


def _scratch_name() -> str:
    # Unique-ish: pid keeps concurrent runs from colliding; the fixed prefix
    # makes any orphaned scratch DB easy to spot and drop.
    return f"buddi_migsmoke_{os.getpid()}"


def _wait_for_server(admin_url: str, attempts: int = 20, delay: float = 1.0) -> bool:
    """Best-effort wait so the script tolerates a just-started container."""
    eng = create_engine(admin_url, isolation_level="AUTOCOMMIT", pool_pre_ping=True)
    try:
        for i in range(attempts):
            try:
                with eng.connect() as conn:
                    conn.execute(text("SELECT 1"))
                return True
            except Exception as exc:  # noqa: BLE001 — surface only after retries
                if i == attempts - 1:
                    print(f"[migrate_smoke] server unreachable: {exc}", file=sys.stderr)
                    return False
                time.sleep(delay)
    finally:
        eng.dispose()
    return False


def _run_alembic(db_url: str, *alembic_args: str) -> int:
    env = dict(os.environ)
    env["DATABASE_URL"] = db_url
    # BUDDI_TEST_MODE lets core.config fill mandatory secrets so env.py import
    # succeeds; it does NOT affect the DDL the migrations emit.
    env.setdefault("BUDDI_TEST_MODE", "1")
    cmd = [sys.executable, "-m", "alembic", "-c", str(ALEMBIC_INI), *alembic_args]
    print(f"[migrate_smoke] $ {' '.join(alembic_args)}")
    return subprocess.call(cmd, env=env, cwd=str(ROOT))


def _verify_invariants(scratch_url: str) -> list[str]:
    """Return a list of human-readable problems (empty == healthy)."""
    problems: list[str] = []
    eng = create_engine(scratch_url, pool_pre_ping=True)
    try:
        with eng.connect() as conn:
            cols = {
                (r[0], r[1])
                for r in conn.execute(
                    text(
                        "SELECT table_name, column_name FROM information_schema.columns "
                        "WHERE table_schema='public'"
                    )
                )
            }
            tables = {tc[0] for tc in cols}
            for tbl in _TENANT_ID_TABLES:
                if tbl not in tables:
                    problems.append(f"missing table: {tbl}")
                elif (tbl, "tenant_id") not in cols:
                    problems.append(f"{tbl} is missing tenant_id")

            # audit_events must be partitioned (relkind 'p').
            relkind = conn.execute(
                text("SELECT relkind FROM pg_class WHERE relname='audit_events'")
            ).scalar()
            if relkind != "p":
                problems.append(
                    f"audit_events relkind={relkind!r} (expected 'p' / partitioned)"
                )

            # RLS policies should exist for the tenant-scoped tables.
            policy_count = conn.execute(
                text(
                    "SELECT count(*) FROM pg_policies "
                    "WHERE policyname LIKE '%tenant_isolation'"
                )
            ).scalar()
            if not policy_count or policy_count < 10:
                problems.append(f"too few RLS policies: {policy_count}")
    finally:
        eng.dispose()
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--roundtrip",
        action="store_true",
        help="Also run `downgrade base` then `upgrade head` to prove reversibility.",
    )
    parser.add_argument(
        "--keep",
        action="store_true",
        help="Do not drop the scratch database (for debugging).",
    )
    args = parser.parse_args(argv)

    admin_url = _resolve_admin_url()
    if not admin_url:
        print(
            "[migrate_smoke] No MIGRATION_SMOKE_DATABASE_URL or DATABASE_URL set.",
            file=sys.stderr,
        )
        return 2

    if not _wait_for_server(admin_url):
        return 1

    parsed = make_url(admin_url)
    scratch_db = _scratch_name()
    # render_as_string(hide_password=False): SQLAlchemy's str(URL) masks the
    # password as '***', which would silently break the connection.
    scratch_url = parsed.set(database=scratch_db).render_as_string(hide_password=False)
    # Admin ops (CREATE/DROP DATABASE) cannot run inside the target DB or a
    # transaction — connect to the maintenance DB in AUTOCOMMIT.
    maint_url = parsed.set(database="postgres").render_as_string(hide_password=False)

    admin_eng = create_engine(maint_url, isolation_level="AUTOCOMMIT")
    rc = 1
    try:
        with admin_eng.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{scratch_db}" WITH (FORCE)'))
            conn.execute(text(f'CREATE DATABASE "{scratch_db}"'))
        print(f"[migrate_smoke] created scratch database {scratch_db}")

        if _run_alembic(scratch_url, "upgrade", "head") != 0:
            print("[migrate_smoke] FAIL: upgrade head returned non-zero", file=sys.stderr)
            return 1

        problems = _verify_invariants(scratch_url)
        if problems:
            print("[migrate_smoke] FAIL: schema invariants violated:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            return 1
        print("[migrate_smoke] OK: upgrade head succeeded; invariants hold")

        if args.roundtrip:
            if _run_alembic(scratch_url, "downgrade", "base") != 0:
                print("[migrate_smoke] FAIL: downgrade base failed", file=sys.stderr)
                return 1
            if _run_alembic(scratch_url, "upgrade", "head") != 0:
                print("[migrate_smoke] FAIL: re-upgrade head failed", file=sys.stderr)
                return 1
            if _verify_invariants(scratch_url):
                print("[migrate_smoke] FAIL: invariants broke after round-trip", file=sys.stderr)
                return 1
            print("[migrate_smoke] OK: downgrade base + upgrade head round-trip clean")

        rc = 0
    finally:
        if not args.keep:
            try:
                with admin_eng.connect() as conn:
                    conn.execute(
                        text(f'DROP DATABASE IF EXISTS "{scratch_db}" WITH (FORCE)')
                    )
                print(f"[migrate_smoke] dropped scratch database {scratch_db}")
            except Exception as exc:  # noqa: BLE001
                print(f"[migrate_smoke] WARN: could not drop {scratch_db}: {exc}", file=sys.stderr)
        admin_eng.dispose()
    return rc


if __name__ == "__main__":
    sys.exit(main())
