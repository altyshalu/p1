"""rename work order constraints

Revision ID: 20260525_0004
Revises: 20260525_0003
Create Date: 2026-05-25
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20260525_0004"
down_revision: str | None = "20260525_0003"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("alter table work_orders rename constraint task_contracts_pkey to work_orders_pkey")
    op.execute("alter table work_orders rename constraint task_contracts_run_id_fkey to work_orders_run_id_fkey")


def downgrade() -> None:
    op.execute("alter table work_orders rename constraint work_orders_pkey to task_contracts_pkey")
    op.execute("alter table work_orders rename constraint work_orders_run_id_fkey to task_contracts_run_id_fkey")
