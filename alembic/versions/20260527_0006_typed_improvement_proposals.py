"""add typed improvement proposal metadata

Revision ID: 20260527_0006
Revises: 20260527_0005
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260527_0006"
down_revision: str | None = "20260527_0005"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("improvement_proposals", sa.Column("target_component", sa.String(length=160), server_default="unknown", nullable=False))
    op.add_column("improvement_proposals", sa.Column("failure_signature", sa.String(length=160), server_default="unknown", nullable=False))
    op.create_index(op.f("ix_improvement_proposals_target_component"), "improvement_proposals", ["target_component"], unique=False)
    op.create_index(op.f("ix_improvement_proposals_failure_signature"), "improvement_proposals", ["failure_signature"], unique=False)
    op.alter_column("improvement_proposals", "target_component", server_default=None)
    op.alter_column("improvement_proposals", "failure_signature", server_default=None)


def downgrade() -> None:
    op.drop_index(op.f("ix_improvement_proposals_failure_signature"), table_name="improvement_proposals")
    op.drop_index(op.f("ix_improvement_proposals_target_component"), table_name="improvement_proposals")
    op.drop_column("improvement_proposals", "failure_signature")
    op.drop_column("improvement_proposals", "target_component")
