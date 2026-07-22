"""Tests for the build-out B7 audit_events partitioning + verify shortcut.

The partition-routing checks require a live Postgres with migrations applied
(``alembic upgrade head``), so they skip when no test DB is present — CI runs
them. They confirm ``audit_events`` is a partitioned parent and that writes
route into a monthly leaf partition rather than the catch-all default.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from core.database import SessionLocal


def _db_or_skip():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1"))
    except Exception as exc:
        db.close()
        pytest.skip(f"test Postgres unavailable: {exc}")
    return db


def test_audit_events_is_a_partitioned_table():
    db = _db_or_skip()
    try:
        relkind = db.execute(
            text("SELECT relkind FROM pg_class WHERE relname = 'audit_events'")
        ).scalar()
        # 'p' = partitioned table (vs 'r' = ordinary table).
        assert relkind == "p"
    finally:
        db.close()


def test_audit_events_has_at_least_one_monthly_partition():
    db = _db_or_skip()
    try:
        n = db.execute(
            text(
                """
                SELECT count(*)
                FROM pg_inherits i
                JOIN pg_class parent ON parent.oid = i.inhparent
                WHERE parent.relname = 'audit_events'
                """
            )
        ).scalar()
        # current + next month partitions (+ default) are created by the migration.
        assert (n or 0) >= 1
    finally:
        db.close()


def test_insert_routes_into_a_monthly_partition():
    db = _db_or_skip()
    try:
        # Insert a system event for "now" and confirm it physically lands in a
        # monthly partition (audit_events_yYYYY_mMM), not audit_events_default.
        row = db.execute(
            text(
                """
                INSERT INTO audit_events (event_type, payload, timestamp)
                VALUES ('partition_routing_test', '{}'::jsonb, now())
                RETURNING tableoid::regclass::text AS partition, event_id
                """
            )
        ).first()
        db.commit()
        assert row is not None
        assert row.partition.startswith("audit_events_y"), row.partition
        assert row.partition != "audit_events_default"
        # Clean up the probe row.
        db.execute(
            text("DELETE FROM audit_events WHERE event_id = :eid"),
            {"eid": row.event_id},
        )
        db.commit()
    finally:
        db.close()
