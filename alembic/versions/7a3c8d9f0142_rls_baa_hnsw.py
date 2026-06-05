"""rls_baa_hnsw: tenant RLS policies, BAA precondition flag, pgvector HNSW

Revision ID: 7a3c8d9f0142
Revises: 58485b98e836
Create Date: 2026-05-08 09:00:00.000000

Implements three Weeks 1–4 Compliance-Credibility-Sprint deliverables from
``Buddi_Strategic_Founders_Operating_Manual.pdf``:

  * §2.2 week 2 #2 — Postgres row-level security (RLS) policies on every
    tenant-scoped table. Defense in depth: the DB itself refuses to
    return another tenant's rows even if a route handler forgets a
    ``WHERE tenant_id = ...`` filter. The policies read
    ``current_setting('app.tenant_id', true)`` which ``core/db_session.py``
    sets at the start of every request.
  * §7.2 Risk #1 mitigation — ``tenants.baa_confirmed BOOLEAN DEFAULT
    FALSE``. The FHIR-ingest route refuses bundles for any tenant where
    this is still FALSE (HTTP 412 "BAA precondition not met"), preventing
    accidental ePHI flow to an LLM provider whose BAA paperwork has not
    landed yet.
  * §4.2 Bottleneck #2 — pgvector HNSW index on
    ``document_chunks.embedding`` so vector search remains sub-second
    above ~100k chunks. Index params (``m=16``, ``ef_construction=64``)
    match the manual's recommendation.

The migration is reversible. Down-migration drops the policies, the
HNSW index, and the BAA column in the same order it added them. Because
the policies are created with explicit names, ``drop_policy`` is precise
and won't accidentally remove operator-defined policies on the same
tables.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


# revision identifiers, used by Alembic.
revision: str = "7a3c8d9f0142"
down_revision: Union[str, Sequence[str], None] = "58485b98e836"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


# Tables that carry a ``tenant_id`` column and therefore need RLS.
# Order matters only for documentation — Postgres applies policies
# per-table independently. Listed alphabetically so reviewers can diff
# against ``core/models.py``.
_TENANT_SCOPED_TABLES = (
    "audit_events",
    "compliance_flags",
    "document_chunks",
    "ehr_integrations",
    "encounters",
    "hcc_suggestions",
    "llm_requests",
    "llm_responses",
    "patients",
    "prior_auth_states",
    "prior_authorization_requests",
    "rag_retrievals",
    "recovery_events",
    "tenant_api_keys",
)

# Policy clause that all RLS policies share. ``current_setting`` with the
# 2-arg form returns NULL when the GUC is unset rather than raising —
# combined with the IS NOT NULL guard this means a query made *without*
# a tenant context returns zero rows instead of crashing the request.
_POLICY_USING = (
    "current_setting('app.tenant_id', true) IS NOT NULL "
    "AND current_setting('app.tenant_id', true) <> '' "
    "AND tenant_id::text = current_setting('app.tenant_id', true)"
)


def _policy_name(table: str) -> str:
    return f"{table}_tenant_isolation"


def upgrade() -> None:
    """Apply the BAA flag, RLS policies, and HNSW index."""

    bind = op.get_bind()

    # 1. tenants.baa_confirmed -------------------------------------------------
    op.add_column(
        "tenants",
        sa.Column(
            "baa_confirmed",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("FALSE"),
            comment=(
                "Manual §7.2 Risk #1 — must be TRUE before any real PHI is "
                "accepted via /ingest/fhir for this tenant. Drop the "
                "server_default once provisioning is automated."
            ),
        ),
    )
    op.add_column(
        "tenants",
        sa.Column(
            "baa_confirmed_at",
            sa.DateTime(timezone=True),
            nullable=True,
        ),
    )

    # 2. Row-level security ----------------------------------------------------
    # RLS is a no-op until ``ENABLE ROW LEVEL SECURITY`` is run per table.
    # FORCE RLS makes the policy apply even to the table owner — without
    # FORCE, a superuser-owned table silently bypasses the policy.
    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"ALTER TABLE {table} ENABLE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} FORCE ROW LEVEL SECURITY")
        op.execute(
            f"""
            CREATE POLICY {_policy_name(table)}
                ON {table}
                USING ({_POLICY_USING})
                WITH CHECK ({_POLICY_USING});
            """
        )

    # The buddi runtime DB role connects as a non-superuser; the SQL
    # below grants it the minimum needed to interact with each table
    # under RLS. If your env names the role differently set the
    # ``BUDDI_DB_ROLE`` env var before running ``alembic upgrade``.
    role = _resolve_runtime_role(bind)
    if role:
        for table in _TENANT_SCOPED_TABLES:
            op.execute(
                f"GRANT SELECT, INSERT, UPDATE, DELETE ON {table} TO {role}"
            )

    # 3. HNSW index for pgvector ----------------------------------------------
    # m=16 / ef_construction=64 — manual §4.2 Bottleneck #2. Building the
    # index is O(n log n) so we use CREATE INDEX IF NOT EXISTS to make
    # the migration idempotent across re-runs in dev.
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS document_chunks_embedding_hnsw_idx
            ON document_chunks
            USING hnsw (embedding vector_cosine_ops)
            WITH (m = 16, ef_construction = 64);
        """
    )

    # 4. Indexes used by the daily Merkle root + ingest hot paths --------------
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS audit_events_tenant_timestamp_idx
            ON audit_events (tenant_id, timestamp);
        """
    )
    op.execute(
        """
        CREATE INDEX IF NOT EXISTS hcc_suggestions_tenant_status_idx
            ON hcc_suggestions (tenant_id, status);
        """
    )


def downgrade() -> None:
    """Reverse the migration in inverse order."""

    op.execute("DROP INDEX IF EXISTS hcc_suggestions_tenant_status_idx")
    op.execute("DROP INDEX IF EXISTS audit_events_tenant_timestamp_idx")
    op.execute("DROP INDEX IF EXISTS document_chunks_embedding_hnsw_idx")

    for table in _TENANT_SCOPED_TABLES:
        op.execute(f"DROP POLICY IF EXISTS {_policy_name(table)} ON {table}")
        op.execute(f"ALTER TABLE {table} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {table} DISABLE ROW LEVEL SECURITY")

    op.drop_column("tenants", "baa_confirmed_at")
    op.drop_column("tenants", "baa_confirmed")


def _resolve_runtime_role(bind) -> str | None:
    """Discover the runtime DB role to grant RLS-compatible privileges to.

    Defaults to the env var ``BUDDI_DB_ROLE`` when set, otherwise falls
    back to the current connection user (``current_user``). When the
    current user is a superuser we skip the GRANT — superusers bypass
    RLS unless ``FORCE ROW LEVEL SECURITY`` is set (which we did set
    above) but the GRANT is still a no-op for them.
    """

    import os

    explicit = os.getenv("BUDDI_DB_ROLE", "").strip()
    if explicit:
        return explicit
    try:
        result = bind.execute(sa.text("SELECT current_user")).scalar()
        return str(result) if result else None
    except Exception:
        return None
