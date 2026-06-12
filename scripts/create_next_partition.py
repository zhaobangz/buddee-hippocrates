"""Ensure the next month's ``audit_events`` partition exists.

Cron entry (run on the 25th of every month so we have ~5 days of slack
if it fails):

    0 3 25 * *  cd /app && /app/venv/bin/python -m scripts.create_next_partition

The script is **idempotent** — every CREATE uses ``IF NOT EXISTS`` — so
re-running it (or running it after a partial failure) is safe. It
creates one RANGE-by-month partition and its ``HASH_MODULUS``
sub-partitions, matching the layout from migration
``c4f1e2d3a5b6_partition_audit_events.py``.

By default it creates the partition that covers ``today + 1 month``.
Pass ``--months N`` to create N consecutive future months at once
(useful for backfilling after a long cron outage). Pass ``--dry-run``
to print the DDL without executing it.

Exit codes:
    0  — partition exists (created or already present)
    1  — DDL failed (alerts should fire on this; partition will fall
         into ``audit_events_default`` until the next successful run)
"""

from __future__ import annotations

import argparse
import logging
import sys
from datetime import datetime, timezone

from sqlalchemy import text

# Reuse the engine factory from the runtime — same DATABASE_URL,
# pool sizing, and SEC-04 credential check.
from core.database import engine


logger = logging.getLogger("create_next_partition")

# MUST match HASH_MODULUS in c4f1e2d3a5b6_partition_audit_events.py.
# Changing this requires rewriting every existing partition; treat as a
# breaking-change migration if it ever needs to move.
HASH_MODULUS = 4


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


def _ddl_for(month_start: datetime) -> list[str]:
    month_end = _add_months(month_start, 1)
    name = _partition_name(month_start)
    statements = [
        (
            f"CREATE TABLE IF NOT EXISTS {name} "
            f"PARTITION OF audit_events "
            f"FOR VALUES FROM ('{month_start.isoformat()}') "
            f"TO ('{month_end.isoformat()}') "
            f"PARTITION BY HASH (tenant_id)"
        )
    ]
    for remainder in range(HASH_MODULUS):
        statements.append(
            f"CREATE TABLE IF NOT EXISTS {name}_h{remainder} "
            f"PARTITION OF {name} "
            f"FOR VALUES WITH (modulus {HASH_MODULUS}, remainder {remainder})"
        )
    return statements


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--months",
        type=int,
        default=1,
        help="Number of consecutive future months to create (default 1).",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print DDL without executing.",
    )
    parser.add_argument(
        "--from",
        dest="from_date",
        type=str,
        default=None,
        help="Start month as YYYY-MM (default: next month from today).",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Log every DDL statement at INFO level.",
    )
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.from_date:
        try:
            year_str, month_str = args.from_date.split("-")
            start = datetime(int(year_str), int(month_str), 1, tzinfo=timezone.utc)
        except (ValueError, TypeError):
            parser.error(f"--from must be YYYY-MM, got {args.from_date!r}")
    else:
        start = _add_months(_floor_to_month(datetime.now(timezone.utc)), 1)

    months = [
        _add_months(start, offset)
        for offset in range(max(1, args.months))
    ]

    all_statements = []
    for month in months:
        all_statements.extend(_ddl_for(month))

    if args.dry_run:
        for stmt in all_statements:
            print(stmt + ";")
        return 0

    try:
        with engine.begin() as conn:
            for stmt in all_statements:
                logger.info("executing: %s", stmt)
                conn.execute(text(stmt))
    except Exception:
        logger.exception("Partition creation failed")
        return 1

    for month in months:
        logger.warning(
            "audit_events partition ensured: %s (HASH modulus=%d)",
            _partition_name(month),
            HASH_MODULUS,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
