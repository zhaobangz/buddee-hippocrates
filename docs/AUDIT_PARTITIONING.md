# Audit-Events Partition Maintenance

`audit_events` is the largest growing table in the Buddi data model.
The Strategic Manual §4.2 Bottleneck #4 forecasts ~5M rows/week at 50
tenants. To keep `GET /api/audit/verify` and the daily Merkle-root
seal job sub-second at that scale, the table is partitioned.

## Layout

Created by migration `c4f1e2d3a5b6_partition_audit_events.py`.

* **Parent:** `audit_events` — RANGE-partitioned on `timestamp`.
* **Monthly partitions:** `audit_events_yYYYY_mMM`, themselves
  HASH-sub-partitioned on `tenant_id` with `modulus 4`.
* **Hash leaves:** `audit_events_yYYYY_mMM_hN` for `N` in `0..3`. These
  are the actual heap files that hold rows.
* **Default partition:** `audit_events_default`. Catches rows whose
  `timestamp` falls outside every declared monthly range. Should be
  **empty** in steady state — non-zero row count here means the cron
  fell behind.

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

## Changing the HASH modulus

**Don't.** Postgres requires every sub-partition of `audit_events_*`
to share the same `(modulus, remainder)` declaration. Changing the
modulus means rewriting every existing partition — a multi-hour
maintenance window at production volumes. If 4 buckets becomes
insufficient, treat the change as a v2 schema migration with a
parallel-table cutover.
