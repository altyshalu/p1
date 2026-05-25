"""registry marketplace tables

Revision ID: 20260525_0002
Revises: 20260524_0001
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "20260525_0002"
down_revision: str | None = "20260524_0001"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "registry_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("version", sa.String(length=40), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("spec", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("kind", "key", name="uq_registry_items_kind_key"),
    )
    op.create_index(op.f("ix_registry_items_kind"), "registry_items", ["kind"])
    op.create_index(op.f("ix_registry_items_key"), "registry_items", ["key"])
    op.create_index(op.f("ix_registry_items_status"), "registry_items", ["status"])

    op.create_table(
        "registry_change_candidates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("kind", sa.String(length=40), nullable=False),
        sa.Column("key", sa.String(length=120), nullable=False),
        sa.Column("change_type", sa.String(length=80), nullable=False),
        sa.Column("status", sa.String(length=40), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_registry_change_candidates_change_type"), "registry_change_candidates", ["change_type"])
    op.create_index(op.f("ix_registry_change_candidates_kind"), "registry_change_candidates", ["kind"])
    op.create_index(op.f("ix_registry_change_candidates_key"), "registry_change_candidates", ["key"])
    op.create_index(op.f("ix_registry_change_candidates_status"), "registry_change_candidates", ["status"])


def downgrade() -> None:
    op.drop_index(op.f("ix_registry_change_candidates_status"), table_name="registry_change_candidates")
    op.drop_index(op.f("ix_registry_change_candidates_key"), table_name="registry_change_candidates")
    op.drop_index(op.f("ix_registry_change_candidates_kind"), table_name="registry_change_candidates")
    op.drop_index(op.f("ix_registry_change_candidates_change_type"), table_name="registry_change_candidates")
    op.drop_table("registry_change_candidates")
    op.drop_index(op.f("ix_registry_items_status"), table_name="registry_items")
    op.drop_index(op.f("ix_registry_items_key"), table_name="registry_items")
    op.drop_index(op.f("ix_registry_items_kind"), table_name="registry_items")
    op.drop_table("registry_items")
