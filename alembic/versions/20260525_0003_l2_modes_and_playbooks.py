"""l2 modes and playbooks

Revision ID: 20260525_0003
Revises: 20260525_0002
Create Date: 2026-05-25
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "20260525_0003"
down_revision: str | None = "20260525_0002"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column("process_runs", sa.Column("playbook_key", sa.String(length=100), nullable=True))
    op.add_column("process_runs", sa.Column("l2_mode", sa.String(length=40), nullable=False, server_default="execution"))
    op.alter_column("process_runs", "l2_mode", server_default=None)
    op.execute("update process_runs set playbook_key = process_key")
    op.alter_column("process_runs", "playbook_key", nullable=False)
    op.drop_index(op.f("ix_process_runs_process_key"), table_name="process_runs")
    op.create_index(op.f("ix_process_runs_playbook_key"), "process_runs", ["playbook_key"])
    op.create_index(op.f("ix_process_runs_l2_mode"), "process_runs", ["l2_mode"])
    op.drop_column("process_runs", "process_key")

    op.rename_table("task_contracts", "work_orders")
    op.alter_column("work_orders", "contract", new_column_name="work_order")
    op.execute("alter index ix_task_contracts_run_id rename to ix_work_orders_run_id")
    op.execute("alter index ix_task_contracts_status rename to ix_work_orders_status")
    op.execute("alter index ix_task_contracts_task_type rename to ix_work_orders_task_type")
    op.execute("alter index ix_task_contracts_worker_profile rename to ix_work_orders_worker_profile")

    op.execute("update registry_items set kind = 'playbook' where kind = 'process_pack'")
    op.execute("update registry_change_candidates set kind = 'playbook' where kind = 'process_pack'")
    _rename_json_key("work_orders", "work_order", "side_effect_policy", "external_action_policy")
    _rename_json_key("registry_items", "spec", "side_effect_policy", "external_action_policy")
    _rename_json_key("registry_items", "spec", "side_effect_class", "external_action_class")
    _rename_json_key("registry_change_candidates", "payload", "side_effect_policy", "external_action_policy")
    _rename_json_key("registry_change_candidates", "payload", "side_effect_class", "external_action_class")
    _rename_nested_json_key("work_orders", "work_order", "external_action_policy", "external_side_effects", "external_actions")
    _rename_nested_json_key("registry_items", "spec", "external_action_policy", "external_side_effects", "external_actions")
    _replace_json_text("work_orders", "work_order", "no_publish_side_effect", "no_publish_external_action")
    _replace_json_text("registry_items", "spec", "no_publish_side_effect", "no_publish_external_action")
    _replace_json_text("registry_change_candidates", "payload", "no_publish_side_effect", "no_publish_external_action")
    op.execute("update events set event_type = 'run_started' where event_type = 'process_started'")
    op.execute("update events set event_type = 'run_finished' where event_type = 'process_finished'")
    op.execute("update events set event_type = 'run_failed' where event_type = 'process_failed'")


def downgrade() -> None:
    op.add_column("process_runs", sa.Column("process_key", sa.String(length=100), nullable=True))
    op.execute("update process_runs set process_key = playbook_key")
    op.alter_column("process_runs", "process_key", nullable=False)
    op.drop_index(op.f("ix_process_runs_l2_mode"), table_name="process_runs")
    op.drop_index(op.f("ix_process_runs_playbook_key"), table_name="process_runs")
    op.create_index(op.f("ix_process_runs_process_key"), "process_runs", ["process_key"])
    op.drop_column("process_runs", "l2_mode")
    op.drop_column("process_runs", "playbook_key")

    op.alter_column("work_orders", "work_order", new_column_name="contract")
    op.rename_table("work_orders", "task_contracts")
    op.execute("alter index ix_work_orders_run_id rename to ix_task_contracts_run_id")
    op.execute("alter index ix_work_orders_status rename to ix_task_contracts_status")
    op.execute("alter index ix_work_orders_task_type rename to ix_task_contracts_task_type")
    op.execute("alter index ix_work_orders_worker_profile rename to ix_task_contracts_worker_profile")

    op.execute("update registry_items set kind = 'process_pack' where kind = 'playbook'")
    op.execute("update registry_change_candidates set kind = 'process_pack' where kind = 'playbook'")
    _rename_json_key("task_contracts", "contract", "external_action_policy", "side_effect_policy")
    _rename_json_key("registry_items", "spec", "external_action_policy", "side_effect_policy")
    _rename_json_key("registry_items", "spec", "external_action_class", "side_effect_class")
    _rename_json_key("registry_change_candidates", "payload", "external_action_policy", "side_effect_policy")
    _rename_json_key("registry_change_candidates", "payload", "external_action_class", "side_effect_class")
    _rename_nested_json_key("task_contracts", "contract", "side_effect_policy", "external_actions", "external_side_effects")
    _rename_nested_json_key("registry_items", "spec", "side_effect_policy", "external_actions", "external_side_effects")
    _replace_json_text("task_contracts", "contract", "no_publish_external_action", "no_publish_side_effect")
    _replace_json_text("registry_items", "spec", "no_publish_external_action", "no_publish_side_effect")
    _replace_json_text("registry_change_candidates", "payload", "no_publish_external_action", "no_publish_side_effect")
    op.execute("update events set event_type = 'process_started' where event_type = 'run_started'")
    op.execute("update events set event_type = 'process_finished' where event_type = 'run_finished'")
    op.execute("update events set event_type = 'process_failed' where event_type = 'run_failed'")


def _rename_json_key(table: str, column: str, old_key: str, new_key: str) -> None:
    op.execute(
        f"""
        update {table}
        set {column} = ({column} - '{old_key}') || jsonb_build_object('{new_key}', {column}->'{old_key}')
        where {column} ? '{old_key}'
        """
    )


def _rename_nested_json_key(table: str, column: str, parent_key: str, old_key: str, new_key: str) -> None:
    op.execute(
        f"""
        update {table}
        set {column} = jsonb_set(
            {column},
            '{{{parent_key}}}',
            (({column}->'{parent_key}') - '{old_key}') || jsonb_build_object('{new_key}', {column}->'{parent_key}'->'{old_key}')
        )
        where {column} ? '{parent_key}' and ({column}->'{parent_key}') ? '{old_key}'
        """
    )


def _replace_json_text(table: str, column: str, old_value: str, new_value: str) -> None:
    op.execute(
        f"""
        update {table}
        set {column} = replace({column}::text, '{old_value}', '{new_value}')::jsonb
        where {column}::text like '%{old_value}%'
        """
    )
