"""persist proposal implementation result

Revision ID: 20260527_0008
Revises: 20260527_0007
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260527_0008"
down_revision: str | None = "20260527_0007"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "improvement_proposals",
        sa.Column("implementation_result", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.alter_column("improvement_proposals", "implementation_result", server_default=None)


def downgrade() -> None:
    op.drop_column("improvement_proposals", "implementation_result")
