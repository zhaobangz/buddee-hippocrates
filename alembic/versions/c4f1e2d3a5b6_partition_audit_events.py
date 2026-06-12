"""partition_audit_events: RANGE(timestamp) + HASH(tenant_id) sub-partitions

Revision ID: c4f1e2d3a5b6
Revises: 7a3c8d9f0142
Create Date: 2026-06-07 09:00:00.000000

Implements the §4.2 Bottleneck #4 fix from
``Buddi_Strategic_Founders_Operating_Manual.pdf``:

    "Partition audit_events by tenant_id and timestamp (monthly
    partitions). The daily merkle root deliverable doubles as a
    verification shortcut — you no longer need to re-walk every event;
    you walk the daily roots and then the day-of-interest's events."

At 50 tenants × 10k weekly encounters × ~10 audit events per encounter
the table reaches ~5M rows/week. Without partitioning, ``GET
/api/audit/verify``'s chain re-walk times out.

Partition layout
----------------
* Parent: ``audit_events`` (partitioned by RANGE on ``timestamp``).
* Per-month partition: ``audit_events_yYYYY_mMM``, sub-partitioned by
  HASH on ``tenant_id`` with modulus 4. The modulus is fixed at
  migration time because Postgres requires every monthly partition to
  share it; 4 buckets gives ~12 tenants/bucket at 50 tenants — enough
  parallelism without partition explosion.
* Per-(month, hash) leaf: ``audit_events_yYYYY_mMM_hN`` (N in 0..3).
* ``audit_events_default``: catch-all. The
  ``scripts/create_next_partition.py`` cron is responsible for creating
  next month's partition before the 1st — anything landing in
  ``_default`` is an *alert* signal that the cron failed.

Why ``timestamp`` and not ``created_at``
----------------------------------------
The real ``audit_events`` schema (initial migration ``58485b98e836``)
has *no* ``created_at`` column. The time column is ``timestamp``. The
strategic manual prescribes "partition by tenant_id and timestamp"
which matches reality; the rewrite spec mentioned ``created_at`` was
a misread of the schema.

Hash-chain safety
-----------------
The cryptographic chain depends on ``previous_hash`` referencing the
hash of the previous row in ``event_id`` order. The data copy uses
``ORDER BY event_id ASC`` and explicitly sets ``event_id`` on the new
table; the BIGSERIAL sequence is then ``setval``-bumped past the
existing max so future inserts continue the chain.

Partitioning constraint
-----------------------
Postgres requires the partition key columns to be part of the table's
PRIMARY KEY. The new PK is therefore ``(event_id, timestamp)`` — wider
than before but the ORM still treats ``event_id`` as the logical row
identifier (see comment on ``core/models.py:AuditEvent``).

This migration is reversible. The downgrade copies rows back into a
non-partitioned ``audit_events`` with the original ``(event_id)`` PK.
"""

from __future__ import annotations

import logging
import os
from datetime import datetime, timezone
from typing import Sequence, Tuple, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "c4f1e2d3a5b6"
down_revision: Union[str, Sequence[str], None] = "7a3c8d9f0142"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.partition_audit_events")


# Tunable knobs. HASH_MODULUS is **immutable** after this migration runs —
# every monthly partition declares the same modulus, and changing it later
# requires rewriting every partition.
HASH_MODULUS = 4

# How many future months to pre-create. The cron creates one more each
# month; this buffer protects us if the cron is broken for a week.
FUTURE_MONTHS_BUFFER = 3

# RLS policy must be recreated on the new partitioned table — it does NOT
# transfer across the rename. Kept verbatim from migration
# ``7a3c8d9f0142_rls_baa_hnsw.py`` so reviewers can diff the two.
_POLICY_USING = (
    "current_setting('app.tenant_id', true) IS NOT NULL "
    "AND current_setting('app.tenant_id', true) <> '' "
    "AND tenant_id::text = current_setting('app.tenant_id', true)"
)


def upgrade() -> None:
    bind = op.get_bind()

    # 1. Discover the existing data range so we create exactly the
    #    monthly partitions we need. An empty table starts from the
    #    current month — the cron handles the rest.
    min_ts, max_ts = _existing_timestamp_range(bind)
    start_month = _floor_to_month(min_ts) if min_ts else _floor_to_month(_now_utc())
    end_anchor = max_ts if max_ts else _now_utc()
    last_month_inclusive = _add_months(_floor_to_month(end_anchor), FUTURE_MONTHS_BUFFER)
    logger.info(
        "audit_events partition range: %s -> %s (HASH modulus=%d)",
        start_month.isoformat(),
        last_month_inclusive.isoformat(),
        HASH_MODULUS,
    )

    # 2. Drop the things that hang off the existing table. RLS policy
    #    and indexes evaporate with the rename otherwise — we want
    #    explicit teardown so the downgrade path is symmetrical.
    op.execute("DROP POLICY IF EXISTS audit_events_tenant_isolation ON audit_events")
    op.execute("DROP INDEX IF EXISTS audit_events_tenant_timestamp_idx")
    op.execute("ALTER TABLE audit_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events DISABLE ROW LEVEL SECURITY")

    # 3. Rename the existing heap table out of the way. Its sequence
    #    moves with it so the BIGSERIAL on the new partitioned table
    #    can claim the canonical name.
    op.execute("ALTER TABLE audit_events RENAME TO audit_events_legacy")
    op.execute(
        "ALTER SEQUENCE IF EXISTS audit_events_event_id_seq "
        "RENAME TO audit_events_legacy_event_id_seq"
    )

    # 4. Create the partitioned parent. The PK must include every
    #    partition-key column (timestamp), so it widens from
    #    ``(event_id)`` to ``(event_id, timestamp)``. The ORM still
    #    treats event_id as the logical identifier (it's unique across
    #    the table because of the underlying BIGSERIAL).
    op.execute(
        """
        CREATE TABLE audit_events (
            event_id BIGSERIAL NOT NULL,
            tenant_id UUID,
            patient_id UUID,
            actor_id UUID,
            event_type VARCHAR(100),
            payload JSONB,
            timestamp TIMESTAMPTZ NOT NULL DEFAULT now(),
            cryptographic_hash TEXT,
            previous_hash TEXT,
            PRIMARY KEY (event_id, timestamp),
            CONSTRAINT audit_events_tenant_id_fkey
                FOREIGN KEY (tenant_id) REFERENCES tenants(id),
            CONSTRAINT audit_events_patient_id_fkey
                FOREIGN KEY (patient_id) REFERENCES patients(id)
        ) PARTITION BY RANGE (timestamp);
        """
    )

    # 5. Create every monthly partition + its HASH sub-partitions.
    cursor = start_month
    while cursor <= last_month_inclusive:
        next_month = _add_months(cursor, 1)
        _create_monthly_partition(cursor, next_month)
        cursor = next_month

    # 6. Default partition: safety net only. The cron MUST keep us
    #    ahead of real traffic. Rows landing here trigger an alert.
    op.execute("CREATE TABLE audit_events_default PARTITION OF audit_events DEFAULT")

    # 7. Indexes — these are propagated to every existing and future
    #    sub-partition (PG 11+). DESC matches the dominant access
    #    pattern (most recent events first); the verify endpoint walks
    #    by event_id, which the PK already covers.
    op.execute(
        """
        CREATE INDEX audit_events_tenant_timestamp_idx
            ON audit_events (tenant_id, timestamp DESC);
        """
    )

    # 8. Copy data in event_id order — CRITICAL for hash-chain integrity.
    #    We provide event_id explicitly; the sequence is bumped below.
    op.execute(
        """
        INSERT INTO audit_events (
            event_id, tenant_id, patient_id, actor_id, event_type,
            payload, timestamp, cryptographic_hash, previous_hash
        )
        SELECT event_id, tenant_id, patient_id, actor_id, event_type,
               payload, COALESCE(timestamp, now()),
               cryptographic_hash, previous_hash
        FROM audit_events_legacy
        ORDER BY event_id ASC;
        """
    )

    # 9. Re-anchor the new BIGSERIAL sequence past the highest copied
    #    event_id so subsequent inserts continue the chain without
    #    collision.
    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('audit_events', 'event_id'),
            GREATEST(COALESCE((SELECT MAX(event_id) FROM audit_events), 1), 1),
            true
        );
        """
    )

    # 10. Drop the legacy table (CASCADE clears its now-orphaned sequence).
    op.execute("DROP TABLE audit_events_legacy CASCADE")

    # 11. Re-enable RLS on the new parent. Policies on a partitioned
    #     parent are enforced for queries that go through the parent,
    #     which is how the ORM accesses the table.
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY audit_events_tenant_isolation
            ON audit_events
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING});
        """
    )

    # 12. Restore GRANTs to the runtime role.
    role = _resolve_runtime_role(bind)
    if role:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON audit_events TO {role}"
        )


def downgrade() -> None:
    bind = op.get_bind()

    # 1. Tear down RLS / index on the partitioned table.
    op.execute("DROP POLICY IF EXISTS audit_events_tenant_isolation ON audit_events")
    op.execute("DROP INDEX IF EXISTS audit_events_tenant_timestamp_idx")
    op.execute("ALTER TABLE audit_events NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events DISABLE ROW LEVEL SECURITY")

    # 2. Stash the partitioned table aside.
    op.execute("ALTER TABLE audit_events RENAME TO audit_events_partitioned")

    # 3. Create a fresh non-partitioned heap with the original PK.
    op.execute(
        """
        CREATE TABLE audit_events (
            event_id BIGSERIAL PRIMARY KEY,
            tenant_id UUID REFERENCES tenants(id),
            patient_id UUID REFERENCES patients(id),
            actor_id UUID,
            event_type VARCHAR(100),
            payload JSONB,
            timestamp TIMESTAMPTZ,
            cryptographic_hash TEXT,
            previous_hash TEXT
        );
        """
    )

    # 4. Copy data back, preserving event_id ordering.
    op.execute(
        """
        INSERT INTO audit_events (
            event_id, tenant_id, patient_id, actor_id, event_type,
            payload, timestamp, cryptographic_hash, previous_hash
        )
        SELECT event_id, tenant_id, patient_id, actor_id, event_type,
               payload, timestamp, cryptographic_hash, previous_hash
        FROM audit_events_partitioned
        ORDER BY event_id ASC;
        """
    )

    op.execute(
        """
        SELECT setval(
            pg_get_serial_sequence('audit_events', 'event_id'),
            GREATEST(COALESCE((SELECT MAX(event_id) FROM audit_events), 1), 1),
            true
        );
        """
    )

    # 5. Drop the partitioned variant (CASCADE removes its leaves).
    op.execute("DROP TABLE audit_events_partitioned CASCADE")

    # 6. Restore the original index, RLS policy, and GRANTs.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS audit_events_tenant_timestamp_idx
            ON audit_events (tenant_id, timestamp);
        """
    )
    op.execute("ALTER TABLE audit_events ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE audit_events FORCE ROW LEVEL SECURITY")
    op.execute(
        f"""
        CREATE POLICY audit_events_tenant_isolation
            ON audit_events
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING});
        """
    )
    role = _resolve_runtime_role(bind)
    if role:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON audit_events TO {role}"
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _existing_timestamp_range(bind) -> Tuple[datetime | None, datetime | None]:
    row = bind.execute(
        sa.text("SELECT MIN(timestamp), MAX(timestamp) FROM audit_events")
    ).first()
    return (row[0], row[1]) if row else (None, None)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _floor_to_month(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.replace(
        day=1, hour=0, minute=0, second=0, microsecond=0, tzinfo=timezone.utc
    )


def _add_months(dt: datetime, n: int) -> datetime:
    month_index = dt.month - 1 + n
    year = dt.year + month_index // 12
    month = month_index % 12 + 1
    return dt.replace(year=year, month=month)


def _partition_name(month_start: datetime) -> str:
    return f"audit_events_y{month_start.year:04d}_m{month_start.month:02d}"


def _create_monthly_partition(month_start: datetime, month_end: datetime) -> None:
    """Create one RANGE partition for ``month_start`` plus its HASH leaves.

    Idempotent: ``IF NOT EXISTS`` is used everywhere so a crashed
    migration can be re-run safely. Sub-partitions all share
    ``HASH_MODULUS`` — this constant cannot change without rewriting
    every existing partition.
    """

    name = _partition_name(month_start)
    op.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {name}
            PARTITION OF audit_events
            FOR VALUES FROM ('{month_start.isoformat()}')
                       TO   ('{month_end.isoformat()}')
            PARTITION BY HASH (tenant_id);
        """
    )
    for remainder in range(HASH_MODULUS):
        op.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {name}_h{remainder}
                PARTITION OF {name}
                FOR VALUES WITH (modulus {HASH_MODULUS}, remainder {remainder});
            """
        )


def _resolve_runtime_role(bind) -> str | None:
    """Mirror of the helper in ``7a3c8d9f0142_rls_baa_hnsw.py``.

    Discover the role to GRANT against. ``BUDDI_DB_ROLE`` env wins;
    otherwise fall back to ``current_user``.
    """

    explicit = os.getenv("BUDDI_DB_ROLE", "").strip()
    if explicit:
        return explicit
    try:
        result = bind.execute(sa.text("SELECT current_user")).scalar()
        return str(result) if result else None
    except Exception:
        return None
