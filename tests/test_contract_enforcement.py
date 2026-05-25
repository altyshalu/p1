from uuid import uuid4

import pytest

from l2l3_protocol.core.schemas import TaskContract
from l2l3_protocol.runtime.contracts import ContractValidationError, validate_contract_inputs, validate_contract_output, validate_tool_policy


def contract(**overrides):
    data = {
        "run_id": uuid4(),
        "task_type": "collect",
        "goal": "collect",
        "worker_profile": "collector",
        "inputs": {"signals": ["x"]},
        "output_schema": {"type": "object", "required": ["signals"], "properties": {"signals": {"type": "array"}}},
        "side_effect_policy": {"external_side_effects": "none"},
    }
    data.update(overrides)
    return TaskContract(**data)


def test_contract_input_schema_rejects_missing_required_input() -> None:
    with pytest.raises(ContractValidationError, match="missing required input"):
        validate_contract_inputs(
            contract(inputs={}),
            {"input_schema": {"type": "object", "required": ["signals"]}},
        )


def test_contract_output_schema_rejects_wrong_type() -> None:
    with pytest.raises(ContractValidationError, match="expected array"):
        validate_contract_output(contract(), {"signals": "not-a-list"})


def test_tool_policy_rejects_tool_side_effect_not_allowed_by_contract() -> None:
    with pytest.raises(ContractValidationError, match="External Action"):
        validate_tool_policy(
            contract(allowed_tools=["publisher"]),
            {"compatible_tools": ["publisher"]},
            {"allowed_tools": ["publisher"]},
            {"publisher": {"key": "publisher", "toolset": "publish", "side_effect_class": "external_write"}},
        )
