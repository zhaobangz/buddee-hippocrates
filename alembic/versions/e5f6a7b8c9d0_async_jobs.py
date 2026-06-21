"""async_jobs: queue LLM-bound work outside request lifecycle

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-06-18 12:05:00.000000

Strategy-doc §4.2 Bottleneck #3: synchronous LLM calls make
``POST /api/shadow/audit`` hold HTTP connections open for ~12 seconds and
degrade sharply under concurrent load. This additive migration creates the
``jobs`` queue table drained by the async worker.

Forward-only note: ``downgrade()`` intentionally does not drop the ``jobs``
table or queued job data. It only removes the tenant FK constraint when Alembic
is asked to downgrade all the way to ``base`` so older migrations can drop
``tenants`` without data loss in ``jobs``.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "e5f6a7b8c9d0"
down_revision: Union[str, Sequence[str], None] = "d4e5f6a7b8c9"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_STATUS_CHECK = "jobs_status_check"
_TENANT_FK = "jobs_tenant_id_fkey"


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def _columns(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns(table)}


def _constraint_names(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    bind = op.get_bind()
    insp = sa.inspect(bind)
    names: set[str] = set()
    for getter in (insp.get_foreign_keys, insp.get_check_constraints, insp.get_unique_constraints):
        for constraint in getter(table):
            if constraint.get("name"):
                names.add(constraint["name"])
    return names


def _index_names(table: str) -> set[str]:
    if not _has_table(table):
        return set()
    return {idx["name"] for idx in sa.inspect(op.get_bind()).get_indexes(table)}


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    if not _has_table("jobs"):
        op.create_table(
            "jobs",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                nullable=False,
            ),
            sa.Column("job_type", sa.Text(), nullable=False),
            sa.Column(
                "status",
                sa.Text(),
                nullable=False,
                server_default=sa.text("'pending'"),
            ),
            sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
            sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            sa.Column("error_message", sa.Text(), nullable=True),
            sa.Column("idempotency_key", sa.Text(), nullable=True),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
            sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        )
    else:
        # Idempotent repair path for developer DBs that may have run an earlier
        # draft of this migration under the same revision id.
        cols = _columns("jobs")
        if "error" in cols and "error_message" not in cols:
            op.alter_column("jobs", "error", new_column_name="error_message")
            cols.remove("error")
            cols.add("error_message")
        additions = {
            "job_type": sa.Column("job_type", sa.Text(), nullable=False, server_default="shadow_audit"),
            "status": sa.Column("status", sa.Text(), nullable=False, server_default="pending"),
            "input_payload": sa.Column("input_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'::jsonb")),
            "result_payload": sa.Column("result_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
            "error_message": sa.Column("error_message", sa.Text(), nullable=True),
            "idempotency_key": sa.Column("idempotency_key", sa.Text(), nullable=True),
            "created_at": sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
            "started_at": sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
            "completed_at": sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        }
        for name, column in additions.items():
            if name not in cols:
                op.add_column("jobs", column)
        op.alter_column("jobs", "job_type", server_default=None)
        op.alter_column("jobs", "input_payload", server_default=None)

    constraints = _constraint_names("jobs")
    if _TENANT_FK not in constraints:
        op.create_foreign_key(
            _TENANT_FK,
            "jobs",
            "tenants",
            ["tenant_id"],
            ["id"],
            ondelete="CASCADE",
        )
    if _STATUS_CHECK not in constraints:
        op.create_check_constraint(
            _STATUS_CHECK,
            "jobs",
            "status IN ('pending','processing','completed','failed')",
        )
    if "uq_jobs_idempotency_key" not in constraints:
        op.create_unique_constraint("uq_jobs_idempotency_key", "jobs", ["idempotency_key"])

    indexes = _index_names("jobs")
    if "jobs_pending_idx" not in indexes:
        op.create_index(
            "jobs_pending_idx",
            "jobs",
            ["status", "created_at"],
            postgresql_where=sa.text("status = 'pending'"),
        )
    if "jobs_tenant_idx" not in indexes:
        op.create_index("jobs_tenant_idx", "jobs", ["tenant_id", sa.text("created_at DESC")])


def downgrade() -> None:
    # Forward-only: do not drop the jobs table or queued data.
    if _has_table("jobs") and _TENANT_FK in _constraint_names("jobs"):
        op.drop_constraint(_TENANT_FK, "jobs", type_="foreignkey")