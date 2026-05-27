"""add run diagnostics improvement proposals

Revision ID: 20260527_0005
Revises: 20260525_0004
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260527_0005"
down_revision: str | None = "20260525_0004"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "improvement_proposals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("source_run_id", sa.String(length=80), nullable=False),
        sa.Column("proposal_type", sa.String(length=80), nullable=False),
        sa.Column("problem", sa.String(), nullable=False),
        sa.Column("proposed_change", sa.String(), nullable=False),
        sa.Column("risk", sa.String(), nullable=False),
        sa.Column("success_check", sa.String(), nullable=False),
        sa.Column("evidence", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("rejection_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["process_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_improvement_proposals_run_id"), "improvement_proposals", ["run_id"], unique=False)
    op.create_index(op.f("ix_improvement_proposals_source_run_id"), "improvement_proposals", ["source_run_id"], unique=False)
    op.create_index(op.f("ix_improvement_proposals_proposal_type"), "improvement_proposals", ["proposal_type"], unique=False)
    op.create_index(op.f("ix_improvement_proposals_status"), "improvement_proposals", ["status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_improvement_proposals_status"), table_name="improvement_proposals")
    op.drop_index(op.f("ix_improvement_proposals_proposal_type"), table_name="improvement_proposals")
    op.drop_index(op.f("ix_improvement_proposals_source_run_id"), table_name="improvement_proposals")
    op.drop_index(op.f("ix_improvement_proposals_run_id"), table_name="improvement_proposals")
    op.drop_table("improvement_proposals")
