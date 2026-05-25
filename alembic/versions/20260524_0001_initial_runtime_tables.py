"""initial runtime tables

Revision ID: 20260524_0001
Revises:
Create Date: 2026-05-24
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260524_0001"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "process_runs",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("process_key", sa.String(length=100), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("input", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_process_runs_process_key"), "process_runs", ["process_key"])
    op.create_index(op.f("ix_process_runs_status"), "process_runs", ["status"])

    op.create_table(
        "task_contracts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_type", sa.String(length=100), nullable=False),
        sa.Column("worker_profile", sa.String(length=100), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("goal", sa.String(), nullable=False),
        sa.Column("contract", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["process_runs.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_contracts_run_id"), "task_contracts", ["run_id"])
    op.create_index(op.f("ix_task_contracts_status"), "task_contracts", ["status"])
    op.create_index(op.f("ix_task_contracts_task_type"), "task_contracts", ["task_type"])
    op.create_index(op.f("ix_task_contracts_worker_profile"), "task_contracts", ["worker_profile"])

    op.create_table(
        "artifacts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("artifact_type", sa.String(length=80), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["process_runs.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task_contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_artifacts_artifact_type"), "artifacts", ["artifact_type"])
    op.create_index(op.f("ix_artifacts_run_id"), "artifacts", ["run_id"])
    op.create_index(op.f("ix_artifacts_task_id"), "artifacts", ["task_id"])

    op.create_table(
        "eval_results",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["process_runs.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task_contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_eval_results_run_id"), "eval_results", ["run_id"])
    op.create_index(op.f("ix_eval_results_task_id"), "eval_results", ["task_id"])

    op.create_table(
        "events",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("run_id", sa.Uuid(), nullable=False),
        sa.Column("task_id", sa.Uuid(), nullable=True),
        sa.Column("event_type", sa.String(length=100), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["process_runs.id"]),
        sa.ForeignKeyConstraint(["task_id"], ["task_contracts.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_events_event_type"), "events", ["event_type"])
    op.create_index(op.f("ix_events_run_id"), "events", ["run_id"])
    op.create_index(op.f("ix_events_task_id"), "events", ["task_id"])


def downgrade() -> None:
    op.drop_index(op.f("ix_events_task_id"), table_name="events")
    op.drop_index(op.f("ix_events_run_id"), table_name="events")
    op.drop_index(op.f("ix_events_event_type"), table_name="events")
    op.drop_table("events")
    op.drop_index(op.f("ix_eval_results_task_id"), table_name="eval_results")
    op.drop_index(op.f("ix_eval_results_run_id"), table_name="eval_results")
    op.drop_table("eval_results")
    op.drop_index(op.f("ix_artifacts_task_id"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_run_id"), table_name="artifacts")
    op.drop_index(op.f("ix_artifacts_artifact_type"), table_name="artifacts")
    op.drop_table("artifacts")
    op.drop_index(op.f("ix_task_contracts_worker_profile"), table_name="task_contracts")
    op.drop_index(op.f("ix_task_contracts_task_type"), table_name="task_contracts")
    op.drop_index(op.f("ix_task_contracts_status"), table_name="task_contracts")
    op.drop_index(op.f("ix_task_contracts_run_id"), table_name="task_contracts")
    op.drop_table("task_contracts")
    op.drop_index(op.f("ix_process_runs_status"), table_name="process_runs")
    op.drop_index(op.f("ix_process_runs_process_key"), table_name="process_runs")
    op.drop_table("process_runs")
