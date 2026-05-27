"""add self improvement memory and proof lifecycle

Revision ID: 20260527_0007
Revises: 20260527_0006
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260527_0007"
down_revision: str | None = "20260527_0006"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "improvement_proposals",
        sa.Column("behavior_change_requires_approval", sa.Boolean(), server_default=sa.text("true"), nullable=False),
    )
    op.add_column(
        "improvement_proposals",
        sa.Column("proof_spec", postgresql.JSONB(astext_type=sa.Text()), server_default=sa.text("'{}'::jsonb"), nullable=False),
    )
    op.add_column("improvement_proposals", sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("improvement_proposals", sa.Column("implemented_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("improvement_proposals", sa.Column("proven_at", sa.DateTime(timezone=True), nullable=True))
    op.alter_column("improvement_proposals", "behavior_change_requires_approval", server_default=None)
    op.alter_column("improvement_proposals", "proof_spec", server_default=None)

    op.create_table(
        "failure_learnings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("failure_signature", sa.String(length=160), nullable=False),
        sa.Column("target_component", sa.String(length=160), nullable=False),
        sa.Column("root_cause", sa.String(length=120), nullable=False),
        sa.Column("playbook_key", sa.String(length=100), nullable=True),
        sa.Column("proposal_type", sa.String(length=80), nullable=False),
        sa.Column("learning_summary", sa.String(), nullable=False),
        sa.Column("proposed_next_step", sa.String(), nullable=False),
        sa.Column("risk", sa.String(), nullable=False),
        sa.Column("success_check", sa.String(), nullable=False),
        sa.Column("severity", sa.String(length=40), nullable=False),
        sa.Column("occurrence_count", sa.Integer(), nullable=False),
        sa.Column("first_seen_run_id", sa.String(length=80), nullable=False),
        sa.Column("last_seen_run_id", sa.String(length=80), nullable=False),
        sa.Column("evidence_refs", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("run_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("failure_signature", "target_component", name="uq_failure_learnings_signature_target"),
    )
    op.create_index(op.f("ix_failure_learnings_failure_signature"), "failure_learnings", ["failure_signature"], unique=False)
    op.create_index(op.f("ix_failure_learnings_target_component"), "failure_learnings", ["target_component"], unique=False)
    op.create_index(op.f("ix_failure_learnings_root_cause"), "failure_learnings", ["root_cause"], unique=False)
    op.create_index(op.f("ix_failure_learnings_playbook_key"), "failure_learnings", ["playbook_key"], unique=False)
    op.create_index(op.f("ix_failure_learnings_proposal_type"), "failure_learnings", ["proposal_type"], unique=False)
    op.create_index(op.f("ix_failure_learnings_severity"), "failure_learnings", ["severity"], unique=False)
    op.create_index(op.f("ix_failure_learnings_last_seen_run_id"), "failure_learnings", ["last_seen_run_id"], unique=False)
    op.create_index(op.f("ix_failure_learnings_status"), "failure_learnings", ["status"], unique=False)

    op.create_table(
        "system_reviews",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("scope", sa.String(length=80), nullable=False),
        sa.Column("playbook_key", sa.String(length=100), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.Column("learning_count", sa.Integer(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_system_reviews_scope"), "system_reviews", ["scope"], unique=False)
    op.create_index(op.f("ix_system_reviews_playbook_key"), "system_reviews", ["playbook_key"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_system_reviews_playbook_key"), table_name="system_reviews")
    op.drop_index(op.f("ix_system_reviews_scope"), table_name="system_reviews")
    op.drop_table("system_reviews")

    op.drop_index(op.f("ix_failure_learnings_status"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_last_seen_run_id"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_severity"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_proposal_type"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_playbook_key"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_root_cause"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_target_component"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_failure_signature"), table_name="failure_learnings")
    op.drop_table("failure_learnings")

    op.drop_column("improvement_proposals", "proven_at")
    op.drop_column("improvement_proposals", "implemented_at")
    op.drop_column("improvement_proposals", "approved_at")
    op.drop_column("improvement_proposals", "proof_spec")
    op.drop_column("improvement_proposals", "behavior_change_requires_approval")
