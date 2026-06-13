# Audit-Events Partition Maintenance

`audit_events` is the largest growing table in the Buddi data model.
The Strategic Manual §4.2 Bottleneck #4 forecasts ~5M rows/week at 50
tenants. To keep `GET /api/audit/verify` and the daily Merkle-root
seal job sub-second at that scale, the table is partitioned.

## Layout

Created by migration `c4f1e2d3a5b6_partition_audit_events.py` (which runs
after `b1f2c3d4e5a6` and `7a3c8d9f0142` in the chain — see
[migration order](#migration-order)).

* **Parent:** `audit_events` — RANGE-partitioned on `timestamp`.
* **Monthly partitions:** `audit_events_yYYYY_mMM` — leaf heap tables that
  hold that month's rows directly.
* **Default partition:** `audit_events_default`. Catches rows whose
  `timestamp` falls outside every declared monthly range. Should be
  **empty** in steady state — non-zero row count here means the cron
  fell behind.

> **No HASH(tenant_id) sub-partitioning.** An earlier draft sub-partitioned
> each month by `HASH (tenant_id)`. That is incompatible with the schema:
> Postgres requires every partition-key column — at every level — to be in
> the PRIMARY KEY, and PK columns are `NOT NULL`, but `audit_events.tenant_id`
> is **nullable** (system / cross-tenant events such as Merkle-root seals are
> written with `tenant_id = NULL`). Monthly RANGE partitioning already bounds
> partition size and enables `timestamp` pruning; the
> `(tenant_id, timestamp DESC)` index serves per-tenant reads. See the
> migration docstring for the full rationale.

The PK is `(event_id, timestamp)` because Postgres requires the
partition key to be part of the primary key. The ORM (`core/models.py`
`AuditEvent`) still treats `event_id` as the logical row identifier.

## Routine maintenance

The cron script creates next month's partition. Default schedule:

```cron
# /etc/cron.d/buddi-audit-partitions
0 3 25 * * buddi cd /app && /app/venv/bin/python -m scripts.create_next_partition
```

The script is **idempotent** (`CREATE TABLE IF NOT EXISTS`). Re-running
after a partial failure is safe. Operational behaviour:

| Flag           | Effect                                                  |
|----------------|---------------------------------------------------------|
| (default)      | Create the single partition for today + 1 month.        |
| `--months 3`   | Create three consecutive future months (backfill mode). |
| `--from YYYY-MM` | Anchor the start month explicitly.                    |
| `--dry-run`    | Print DDL without executing.                            |
| `--verbose`    | INFO-level logging of every DDL statement.              |

Exit codes:

* `0` — partition exists (whether created now or already present)
* `1` — DDL failed; alert immediately. Rows will land in
  `audit_events_default` until the next successful run.

## Alerts to wire up

1. **Default partition row count > 0**:
   ```sql
   SELECT count(*) FROM audit_events_default;
   ```
   Any non-zero value means the cron failed. Page the on-call.
2. **Partition coverage gap**: query
   `pg_partitions` (or `pg_class` + `pg_inherits`) and confirm a
   partition exists for the current month and the next month. CI
   should run this against staging weekly.
3. **Sequence drift**: the BIGSERIAL on `event_id` is shared across
   partitions. If `nextval(...)` drops below `MAX(event_id)` after a
   restore, the chain breaks. The verify endpoint catches this.

## Detaching old partitions

When a tenant's retention window has been satisfied (typical: 7 years
for HIPAA), an old monthly partition can be detached and archived to
cold storage:

```sql
-- Take the partition offline (rows remain in place, just unattached).
ALTER TABLE audit_events DETACH PARTITION audit_events_y2019_m01;

-- Export the chunk to object storage as an immutable artifact.
COPY audit_events_y2019_m01 TO PROGRAM
  'gzip > /tmp/audit_events_y2019_m01.csv.gz';

-- Hand the gzipped CSV + its Merkle root to the Cloud Storage uploader.
-- Only then:
DROP TABLE audit_events_y2019_m01;
```

**Do not skip the export.** The detached partition still contains the
hash chain that future verification jobs reference. Cold-storage
retention is part of the compliance moat (§7.2 Risk #1).

## Verification fast path

The daily signed Merkle roots in `storage/audit_roots/` are the
**preferred** verification path at scale. Walking the roots is
`O(days)` and prunes against the monthly partition that owns each
day; re-walking the raw chain via `_verify_audit_chain` fans out
across every monthly partition.

For pilot-scale tenants, prefer either:

* `verify_signed_roots_against_db()` (the roots check), or
* a chain re-walk with an explicit `WHERE timestamp >= ...` so the
  planner can partition-prune.

`GET /api/audit/verify` still returns the raw-chain `chain` block for
backward compatibility with `frontend/src/pages/AuditPage.jsx`, but
production dashboards should drive their pass/fail off the `roots`
block.

## Migration order

The audit-partitioning migration is the head of a four-revision chain.
A fresh `alembic upgrade head` applies them in this order:

1. `58485b98e836` — initial schema.
2. `b1f2c3d4e5a6` — creates `tenant_api_keys` and the nine missing
   `tenant_id` columns/FKs (closes the ORM/migration drift that used to
   crash the RLS migration on a fresh DB).
3. `7a3c8d9f0142` — RLS policies, `tenants.baa_confirmed`, pgvector HNSW.
4. `c4f1e2d3a5b6` — this migration (monthly RANGE partitioning).

`scripts/migrate_smoke.py` (and `tests/test_migrations.py`) run this whole
chain against a throwaway database to guard the order against regressions.

## If monthly partitions become too large

Monthly RANGE partitions bound each partition to one month of rows. If a
single month becomes unwieldy at much higher tenant counts, the options
are weekly RANGE partitioning or a v2 schema migration with a
parallel-table cutover — *not* HASH sub-partitioning by `tenant_id`, which
is incompatible with the nullable `tenant_id` column (see Layout above).
