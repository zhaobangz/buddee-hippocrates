"""billing_columns: Stripe billing fields on tenants (PROMPT_04)

Revision ID: f6a7b8c9d0e1
Revises: e5f6a7b8c9d0
Create Date: 2026-06-18 12:00:00.000000

Strategy-doc §2.1 gap #10: Stripe must be wired before a customer can sign.
Adds the billing columns to ``tenants``:

    stripe_customer_id              TEXT
    subscription_status             TEXT DEFAULT 'none'
    subscription_id                 TEXT
    subscription_current_period_end TIMESTAMPTZ
    physician_count                 INTEGER DEFAULT 1

subscription_status values: none | trialing | active | past_due | canceled

Purely additive and idempotent (each column guarded by an introspection check)
so it is safe on a fresh DB or one where an earlier draft already added a
subset of these columns.
"""

from __future__ import annotations

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "f6a7b8c9d0e1"
down_revision: Union[str, Sequence[str], None] = "e5f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_COLUMNS = {
    "stripe_customer_id": sa.Column("stripe_customer_id", sa.Text(), nullable=True),
    "subscription_status": sa.Column(
        "subscription_status", sa.Text(), nullable=True, server_default="none"
    ),
    "subscription_id": sa.Column("subscription_id", sa.Text(), nullable=True),
    "subscription_current_period_end": sa.Column(
        "subscription_current_period_end", sa.DateTime(timezone=True), nullable=True
    ),
    "physician_count": sa.Column(
        "physician_count", sa.Integer(), nullable=True, server_default="1"
    ),
}


def _existing_columns() -> set[str]:
    return {c["name"] for c in sa.inspect(op.get_bind()).get_columns("tenants")}


def upgrade() -> None:
    existing = _existing_columns()
    for name, column in _COLUMNS.items():
        if name not in existing:
            op.add_column("tenants", column)
    # Indexes for the lookup paths used by the webhook handlers / status route.
    indexes = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("tenants")}
    if "ix_tenants_stripe_customer_id" not in indexes:
        op.create_index("ix_tenants_stripe_customer_id", "tenants", ["stripe_customer_id"])
    if "ix_tenants_subscription_id" not in indexes:
        op.create_index("ix_tenants_subscription_id", "tenants", ["subscription_id"])


def downgrade() -> None:
    indexes = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("tenants")}
    if "ix_tenants_subscription_id" in indexes:
        op.drop_index("ix_tenants_subscription_id", table_name="tenants")
    if "ix_tenants_stripe_customer_id" in indexes:
        op.drop_index("ix_tenants_stripe_customer_id", table_name="tenants")
    existing = _existing_columns()
    for name in (
        "physician_count",
        "subscription_current_period_end",
        "subscription_id",
        "subscription_status",
        "stripe_customer_id",
    ):
        if name in existing:
            op.drop_column("tenants", name)
