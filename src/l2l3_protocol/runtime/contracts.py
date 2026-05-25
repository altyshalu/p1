from __future__ import annotations

from typing import Any

from l2l3_protocol.core.schemas import TaskContract


class ContractValidationError(ValueError):
    def __init__(self, message: str, failure_type: str = "input_validation") -> None:
        super().__init__(message)
        self.failure_type = failure_type


def validate_contract_inputs(contract: TaskContract, profile: dict[str, Any]) -> None:
    _validate_schema(profile.get("input_schema", {}), contract.inputs, "input")


def validate_contract_output(contract: TaskContract, payload: dict[str, Any]) -> None:
    _validate_schema(contract.output_schema, payload, "output")
    _validate_side_effect_report(contract, payload)


def validate_tool_policy(
    contract: TaskContract,
    profile: dict[str, Any],
    process_pack: dict[str, Any],
    tools: dict[str, dict[str, Any]],
) -> list[str]:
    if "compatible_tools" not in profile:
        raise ContractValidationError("worker profile missing compatible_tools", "tool_denied")
    if "allowed_tools" not in process_pack:
        raise ContractValidationError("process pack missing allowed_tools", "tool_denied")
    compatible_tools = set(profile["compatible_tools"])
    process_tools = set(process_pack["allowed_tools"])
    resolved_toolsets: list[str] = []
    for tool_id in contract.allowed_tools:
        if compatible_tools and tool_id not in compatible_tools:
            raise ContractValidationError(f"tool is not compatible with worker: {tool_id}", "tool_denied")
        if process_tools and tool_id not in process_tools:
            raise ContractValidationError(f"tool is not allowed by process pack: {tool_id}", "tool_denied")
        tool = tools.get(tool_id)
        if tool is None:
            raise ContractValidationError(f"unknown tool requested: {tool_id}", "tool_denied")
        _validate_tool_side_effect(contract, tool)
        toolset = tool.get("toolset")
        if toolset:
            resolved_toolsets.append(str(toolset))
    return resolved_toolsets


def _validate_schema(schema: dict[str, Any], value: dict[str, Any], label: str) -> None:
    if not schema:
        return
    if schema.get("type") == "object" and not isinstance(value, dict):
        raise ContractValidationError(f"{label} expected object")
    for key in schema.get("required", []):
        if key not in value:
            raise ContractValidationError(f"missing required {label}: {key}")
    properties = schema.get("properties", {})
    for key, property_schema in properties.items():
        if key not in value:
            continue
        _validate_type(value[key], property_schema.get("type"), f"{label}.{key}")


def _validate_type(value: Any, expected: str | None, path: str) -> None:
    if expected is None:
        return
    checks = {
        "array": list,
        "object": dict,
        "string": str,
        "number": (int, float),
        "integer": int,
        "boolean": bool,
    }
    python_type = checks.get(expected)
    if python_type is not None and not isinstance(value, python_type):
        raise ContractValidationError(f"{path} expected {expected}")


def _validate_tool_side_effect(contract: TaskContract, tool: dict[str, Any]) -> None:
    side_effect_class = tool.get("side_effect_class", "none")
    if side_effect_class in {"none", "read"}:
        return
    policy = contract.side_effect_policy
    if policy.get("external_side_effects") == "none" or policy.get("publish_allowed") is False:
        raise ContractValidationError(f"tool side effect is not allowed: {side_effect_class}", "side_effect_violation")


def _validate_side_effect_report(contract: TaskContract, payload: dict[str, Any]) -> None:
    side_effects = payload.get("side_effects", [])
    if not side_effects:
        return
    policy = contract.side_effect_policy
    if policy.get("external_side_effects") == "none" or policy.get("publish_allowed") is False:
        raise ContractValidationError("output reported unauthorized side effect", "side_effect_violation")
