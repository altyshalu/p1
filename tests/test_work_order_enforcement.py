from uuid import uuid4

import pytest

from l2l3_protocol.core.schemas import WorkOrder
from l2l3_protocol.runtime.work_orders import WorkOrderValidationError, validate_work_order_inputs, validate_work_order_output, validate_tool_policy


def work_order(**overrides):
    data = {
        "run_id": uuid4(),
        "task_type": "collect",
        "goal": "collect",
        "worker_profile": "collector",
        "inputs": {"signals": ["x"]},
        "output_schema": {"type": "object", "required": ["signals"], "properties": {"signals": {"type": "array"}}},
        "external_action_policy": {"external_actions": "none"},
    }
    data.update(overrides)
    return WorkOrder(**data)


def test_work_order_input_schema_rejects_missing_required_input() -> None:
    with pytest.raises(WorkOrderValidationError, match="missing required input"):
        validate_work_order_inputs(
            work_order(inputs={}),
            {"input_schema": {"type": "object", "required": ["signals"]}},
        )


def test_work_order_output_schema_rejects_wrong_type() -> None:
    with pytest.raises(WorkOrderValidationError, match="expected array"):
        validate_work_order_output(work_order(), {"signals": "not-a-list"})


def test_tool_policy_rejects_external_action_not_allowed_by_work_order() -> None:
    with pytest.raises(WorkOrderValidationError, match="External Action"):
        validate_tool_policy(
            work_order(allowed_tools=["publisher"]),
            {"compatible_tools": ["publisher"]},
            {"allowed_tools": ["publisher"]},
            {"publisher": {"key": "publisher", "toolset": "publish", "external_action_class": "external_write"}},
        )
