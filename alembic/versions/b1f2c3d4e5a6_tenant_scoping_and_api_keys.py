"""tenant_scoping_and_api_keys: create tenant_api_keys + backfill tenant_id columns

Revision ID: b1f2c3d4e5a6
Revises: 58485b98e836
Create Date: 2026-06-13 10:00:00.000000

Closes the ORM/migration drift that made a fresh ``alembic upgrade head``
fail at the RLS migration (``7a3c8d9f0142``):

  * ``core/models.py`` defines a ``tenant_api_keys`` table, but no migration
    ever created it. The RLS migration lists it in ``_TENANT_SCOPED_TABLES``
    and runs ``ALTER TABLE tenant_api_keys ENABLE ROW LEVEL SECURITY`` —
    which errors with *relation "tenant_api_keys" does not exist* on a fresh
    database.
  * Nine tenant-scoped tables carry a ``tenant_id`` FK in the ORM but were
    created **without** that column by the initial migration
    (``58485b98e836``). The RLS migration then tries to
    ``CREATE POLICY ... USING (tenant_id::text = ...)`` against tables that
    have no ``tenant_id`` column, which also errors.

This migration is **purely additive** and **idempotent**. It is inserted
*before* the RLS migration (which now has ``down_revision =
b1f2c3d4e5a6``) so the RLS migration finds every table and column it
expects. Every operation is guarded by a live introspection check, so it
is also a safe no-op on databases whose schema was built from
``Base.metadata.create_all`` and then ``alembic stamp``-ed — the historical
source of the drift. No data is read, rewritten, or dropped.
"""

from __future__ import annotations

import logging
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

# revision identifiers, used by Alembic.
revision: str = "b1f2c3d4e5a6"
down_revision: Union[str, Sequence[str], None] = "58485b98e836"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


logger = logging.getLogger("alembic.tenant_scoping_and_api_keys")


# Tenant-scoped tables that the ORM (``core/models.py``) gives a
# ``tenant_id`` FK but the initial migration ``58485b98e836`` created
# without one. Listed in dependency-safe order (parents before children is
# irrelevant for an additive column, but kept alphabetical for review).
_TABLES_NEEDING_TENANT_ID = (
    "billing_codes",
    "clinical_notes",
    "document_chunks",
    "hcc_suggestions",
    "llm_responses",
    "prior_auth_states",
    "prior_authorization_requests",
    "rag_retrievals",
    "recovery_events",
)


def _has_table(bind, table: str) -> bool:
    return sa.inspect(bind).has_table(table)


def _has_column(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    return any(col["name"] == column for col in insp.get_columns(table))


def _has_fk_on(bind, table: str, column: str) -> bool:
    insp = sa.inspect(bind)
    if not insp.has_table(table):
        return False
    for fk in insp.get_foreign_keys(table):
        if column in (fk.get("constrained_columns") or []):
            return True
    return False


def upgrade() -> None:
    bind = op.get_bind()

    # 1. tenant_api_keys -------------------------------------------------------
    # Per-tenant API credential metadata. ``key_hash_sha256`` is a
    # deterministic lookup index; the presented key is then verified against
    # the salted Argon2 ``hashed_key``. Mirrors ``core/models.py:TenantApiKey``.
    if not _has_table(bind, "tenant_api_keys"):
        op.create_table(
            "tenant_api_keys",
            sa.Column("id", sa.UUID(), nullable=False),
            sa.Column("tenant_id", sa.UUID(), nullable=False),
            sa.Column("key_hash_sha256", sa.String(length=64), nullable=False),
            sa.Column("hashed_key", sa.Text(), nullable=False),
            sa.Column("scopes", postgresql.JSONB(astext_type=sa.Text()), nullable=False,
                      server_default=sa.text("'[]'::jsonb")),
            sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
            sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
            sa.ForeignKeyConstraint(
                ["tenant_id"], ["tenants.id"],
                name="tenant_api_keys_tenant_id_fkey",
            ),
            sa.PrimaryKeyConstraint("id", name="tenant_api_keys_pkey"),
            sa.UniqueConstraint("hashed_key", name="uq_tenant_api_keys_hashed_key"),
        )
        # ``key_hash_sha256`` is unique *and* indexed for O(1) credential
        # lookup (unique=True, index=True in the ORM).
        op.create_index(
            "ix_tenant_api_keys_key_hash_sha256",
            "tenant_api_keys",
            ["key_hash_sha256"],
            unique=True,
        )
        # Tenant-scoped queries (list / rotate a tenant's keys) hit this.
        op.create_index(
            "ix_tenant_api_keys_tenant_id",
            "tenant_api_keys",
            ["tenant_id"],
            unique=False,
        )
        logger.info("created table tenant_api_keys")
    else:
        logger.info("tenant_api_keys already present — skipping create")

    # 2. tenant_id columns + FKs on drifted tables -----------------------------
    # Additive only. ``ADD COLUMN`` for a brand-new nullable column is a fast
    # metadata-only change in Postgres (no table rewrite). FK is added
    # separately so we can guard each independently.
    for table in _TABLES_NEEDING_TENANT_ID:
        if not _has_table(bind, table):
            # Should not happen on a chain that ran 58485b98e836 first, but
            # keep the migration robust rather than crashing mid-run.
            logger.warning("table %s missing — skipping tenant_id backfill", table)
            continue

        if not _has_column(bind, table, "tenant_id"):
            op.add_column(table, sa.Column("tenant_id", sa.UUID(), nullable=True))
            logger.info("added %s.tenant_id", table)
        else:
            logger.info("%s.tenant_id already present — skipping column", table)

        if not _has_fk_on(bind, table, "tenant_id"):
            op.create_foreign_key(
                f"{table}_tenant_id_fkey",
                table,
                "tenants",
                ["tenant_id"],
                ["id"],
            )
            logger.info("added FK %s.tenant_id -> tenants.id", table)
        else:
            logger.info("%s.tenant_id FK already present — skipping", table)


def downgrade() -> None:
    bind = op.get_bind()

    # Reverse order. Downgrade runs *after* the RLS migration has already been
    # downgraded (chain: c4f1e2d3a5b6 -> 7a3c8d9f0142 -> b1f2c3d4e5a6 -> ...),
    # so no RLS policy still references these columns at this point.
    for table in _TABLES_NEEDING_TENANT_ID:
        if not _has_table(bind, table):
            continue
        if _has_fk_on(bind, table, "tenant_id"):
            op.drop_constraint(f"{table}_tenant_id_fkey", table, type_="foreignkey")
        if _has_column(bind, table, "tenant_id"):
            op.drop_column(table, "tenant_id")

    if _has_table(bind, "tenant_api_keys"):
        op.drop_index("ix_tenant_api_keys_tenant_id", table_name="tenant_api_keys")
        op.drop_index("ix_tenant_api_keys_key_hash_sha256", table_name="tenant_api_keys")
        op.drop_table("tenant_api_keys")
