"""webhook_endpoints: customer webhook registrations (build-out B2)

Revision ID: d4e5f6a7b8c9
Revises: c4f1e2d3a5b6
Create Date: 2026-06-18 11:00:00.000000

Strategy-doc §2.1 gap #8: webhooks are a day-one integration requirement for
billing customers. This adds the ``webhook_endpoints`` table (one row per
customer-registered target) and enables row-level security on it with the
same tenant-isolation policy the rest of the schema uses
(``7a3c8d9f0142_rls_baa_hnsw``).

The ``secret`` column stores the HMAC signing secret encrypted at rest (via
``core/storage.SecureStorage``), not a one-way hash — outgoing payloads are
signed with HMAC-SHA256 using the raw secret. See ``core/webhooks.py``.

Purely additive and idempotent.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "d4e5f6a7b8c9"
down_revision: Union[str, Sequence[str], None] = "c4f1e2d3a5b6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY_USING = (
    "current_setting('app.tenant_id', true) IS NOT NULL "
    "AND current_setting('app.tenant_id', true) <> '' "
    "AND tenant_id::text = current_setting('app.tenant_id', true)"
)


def _has_table(name: str) -> bool:
    return sa.inspect(op.get_bind()).has_table(name)


def upgrade() -> None:
    if not _has_table("webhook_endpoints"):
        op.create_table(
            "webhook_endpoints",
            sa.Column(
                "id",
                postgresql.UUID(as_uuid=True),
                primary_key=True,
                server_default=sa.text("gen_random_uuid()"),
            ),
            sa.Column(
                "tenant_id",
                postgresql.UUID(as_uuid=True),
                sa.ForeignKey("tenants.id"),
                nullable=False,
            ),
            sa.Column("url", sa.Text(), nullable=False),
            sa.Column("secret", sa.Text(), nullable=False),
            sa.Column("events", postgresql.ARRAY(sa.Text()), nullable=False),
            sa.Column(
                "active",
                sa.Boolean(),
                nullable=False,
                server_default=sa.text("true"),
            ),
            sa.Column(
                "created_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                server_default=sa.text("now()"),
            ),
        )
        op.create_index(
            "ix_webhook_endpoints_tenant_id", "webhook_endpoints", ["tenant_id"]
        )

    # Enable tenant-isolation RLS, matching the rest of the schema.
    op.execute("ALTER TABLE webhook_endpoints ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE webhook_endpoints FORCE ROW LEVEL SECURITY")
    op.execute("DROP POLICY IF EXISTS webhook_endpoints_tenant_isolation ON webhook_endpoints")
    op.execute(
        f"""
        CREATE POLICY webhook_endpoints_tenant_isolation ON webhook_endpoints
            USING ({_POLICY_USING})
            WITH CHECK ({_POLICY_USING});
        """
    )


def downgrade() -> None:
    op.execute("DROP POLICY IF EXISTS webhook_endpoints_tenant_isolation ON webhook_endpoints")
    if _has_table("webhook_endpoints"):
        op.drop_index("ix_webhook_endpoints_tenant_id", table_name="webhook_endpoints")
        op.drop_table("webhook_endpoints")
