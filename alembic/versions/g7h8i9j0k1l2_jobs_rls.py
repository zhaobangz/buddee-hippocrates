"""jobs_rls: enforce tenant isolation on async jobs

Revision ID: g7h8i9j0k1l2
Revises: f6a7b8c9d0e1
Create Date: 2026-06-23 12:00:00.000000
"""

from __future__ import annotations

from typing import Sequence, Union

from alembic import op

revision: str = "g7h8i9j0k1l2"
down_revision: Union[str, Sequence[str], None] = "f6a7b8c9d0e1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_POLICY = "jobs_tenant_or_worker_isolation"
_USING = (
    "current_setting('app.worker_mode', true) = '1' "
    "OR (current_setting('app.tenant_id', true) IS NOT NULL "
    "AND current_setting('app.tenant_id', true) <> '' "
    "AND tenant_id::text = current_setting('app.tenant_id', true))"
)


def upgrade() -> None:
    op.execute("ALTER TABLE jobs ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE jobs FORCE ROW LEVEL SECURITY")
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON jobs")
    op.execute(
        f"""
        CREATE POLICY {_POLICY}
            ON jobs
            USING ({_USING})
            WITH CHECK ({_USING});
        """
    )


def downgrade() -> None:
    op.execute(f"DROP POLICY IF EXISTS {_POLICY} ON jobs")
    op.execute("ALTER TABLE jobs NO FORCE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE jobs DISABLE ROW LEVEL SECURITY")
