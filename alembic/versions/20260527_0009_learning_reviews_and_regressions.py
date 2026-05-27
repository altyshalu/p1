"""expand learning reviews and regression catalog

Revision ID: 20260527_0009
Revises: 20260527_0008
Create Date: 2026-05-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260527_0009"
down_revision: str | None = "20260527_0008"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("failure_learnings", sa.Column("worker_family", sa.String(length=120), nullable=True))
    op.add_column("failure_learnings", sa.Column("eval_family", sa.String(length=120), nullable=True))
    op.add_column("failure_learnings", sa.Column("tool_family", sa.String(length=120), nullable=True))
    op.add_column("failure_learnings", sa.Column("repair_attempt_count", sa.Integer(), server_default="0", nullable=False))
    op.add_column("failure_learnings", sa.Column("human_intervention_count", sa.Integer(), server_default="0", nullable=False))
    op.create_index(op.f("ix_failure_learnings_worker_family"), "failure_learnings", ["worker_family"], unique=False)
    op.create_index(op.f("ix_failure_learnings_eval_family"), "failure_learnings", ["eval_family"], unique=False)
    op.create_index(op.f("ix_failure_learnings_tool_family"), "failure_learnings", ["tool_family"], unique=False)
    op.drop_constraint("uq_failure_learnings_signature_target", "failure_learnings", type_="unique")
    op.create_unique_constraint(
        "uq_failure_learnings_grouping_key",
        "failure_learnings",
        ["failure_signature", "target_component", "playbook_key", "root_cause", "worker_family", "eval_family", "tool_family"],
    )
    op.alter_column("failure_learnings", "repair_attempt_count", server_default=None)
    op.alter_column("failure_learnings", "human_intervention_count", server_default=None)

    op.create_table(
        "regression_cases",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("proposal_id", sa.Uuid(), nullable=False),
        sa.Column("baseline_run_id", sa.String(length=80), nullable=False),
        sa.Column("failure_signature", sa.String(length=160), nullable=False),
        sa.Column("target_component", sa.String(length=160), nullable=False),
        sa.Column("comparable_run_input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("proof_command", sa.String(), nullable=False),
        sa.Column("expected_absent_failure", sa.String(length=160), nullable=False),
        sa.Column("last_after_run_id", sa.String(length=80), nullable=True),
        sa.Column("last_proof_status", sa.String(length=40), nullable=False),
        sa.Column("last_proof_result", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["proposal_id"], ["improvement_proposals.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("proposal_id", name="uq_regression_cases_proposal_id"),
    )
    op.create_index(op.f("ix_regression_cases_proposal_id"), "regression_cases", ["proposal_id"], unique=False)
    op.create_index(op.f("ix_regression_cases_baseline_run_id"), "regression_cases", ["baseline_run_id"], unique=False)
    op.create_index(op.f("ix_regression_cases_failure_signature"), "regression_cases", ["failure_signature"], unique=False)
    op.create_index(op.f("ix_regression_cases_target_component"), "regression_cases", ["target_component"], unique=False)
    op.create_index(op.f("ix_regression_cases_expected_absent_failure"), "regression_cases", ["expected_absent_failure"], unique=False)
    op.create_index(op.f("ix_regression_cases_last_after_run_id"), "regression_cases", ["last_after_run_id"], unique=False)
    op.create_index(op.f("ix_regression_cases_last_proof_status"), "regression_cases", ["last_proof_status"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_regression_cases_last_proof_status"), table_name="regression_cases")
    op.drop_index(op.f("ix_regression_cases_last_after_run_id"), table_name="regression_cases")
    op.drop_index(op.f("ix_regression_cases_expected_absent_failure"), table_name="regression_cases")
    op.drop_index(op.f("ix_regression_cases_target_component"), table_name="regression_cases")
    op.drop_index(op.f("ix_regression_cases_failure_signature"), table_name="regression_cases")
    op.drop_index(op.f("ix_regression_cases_baseline_run_id"), table_name="regression_cases")
    op.drop_index(op.f("ix_regression_cases_proposal_id"), table_name="regression_cases")
    op.drop_table("regression_cases")

    op.drop_constraint("uq_failure_learnings_grouping_key", "failure_learnings", type_="unique")
    op.create_unique_constraint("uq_failure_learnings_signature_target", "failure_learnings", ["failure_signature", "target_component"])
    op.drop_index(op.f("ix_failure_learnings_tool_family"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_eval_family"), table_name="failure_learnings")
    op.drop_index(op.f("ix_failure_learnings_worker_family"), table_name="failure_learnings")
    op.drop_column("failure_learnings", "human_intervention_count")
    op.drop_column("failure_learnings", "repair_attempt_count")
    op.drop_column("failure_learnings", "tool_family")
    op.drop_column("failure_learnings", "eval_family")
    op.drop_column("failure_learnings", "worker_family")
