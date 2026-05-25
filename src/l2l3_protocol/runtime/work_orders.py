from __future__ import annotations

from typing import Any

from l2l3_protocol.core.schemas import WorkOrder


class WorkOrderValidationError(ValueError):
    def __init__(self, message: str, failure_type: str = "input_validation") -> None:
        super().__init__(message)
        self.failure_type = failure_type


def validate_work_order_inputs(work_order: WorkOrder, profile: dict[str, Any]) -> None:
    _validate_schema(profile.get("input_schema", {}), work_order.inputs, "input")


def validate_work_order_output(work_order: WorkOrder, payload: dict[str, Any]) -> None:
    _validate_schema(work_order.output_schema, payload, "output")
    _validate_external_action_report(work_order, payload)


def validate_tool_policy(
    work_order: WorkOrder,
    profile: dict[str, Any],
    playbook: dict[str, Any],
    tools: dict[str, dict[str, Any]],
) -> list[str]:
    if "compatible_tools" not in profile:
        raise WorkOrderValidationError("worker profile missing compatible_tools", "tool_denied")
    if "allowed_tools" not in playbook:
        raise WorkOrderValidationError("Playbook missing allowed_tools", "tool_denied")
    compatible_tools = set(profile["compatible_tools"])
    playbook_tools = set(playbook["allowed_tools"])
    resolved_toolsets: list[str] = []
    for tool_id in work_order.allowed_tools:
        if compatible_tools and tool_id not in compatible_tools:
            raise WorkOrderValidationError(f"tool is not compatible with worker: {tool_id}", "tool_denied")
        if playbook_tools and tool_id not in playbook_tools:
            raise WorkOrderValidationError(f"tool is not allowed by Playbook: {tool_id}", "tool_denied")
        tool = tools.get(tool_id)
        if tool is None:
            raise WorkOrderValidationError(f"unknown tool requested: {tool_id}", "tool_denied")
        _validate_tool_external_action(work_order, tool)
        toolset = tool.get("toolset")
        if toolset:
            resolved_toolsets.append(str(toolset))
    return resolved_toolsets


def _validate_schema(schema: dict[str, Any], value: dict[str, Any], label: str) -> None:
    if not schema:
        return
    if schema.get("type") == "object" and not isinstance(value, dict):
        raise WorkOrderValidationError(f"{label} expected object")
    for key in schema.get("required", []):
        if key not in value:
            raise WorkOrderValidationError(f"missing required {label}: {key}")
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
        raise WorkOrderValidationError(f"{path} expected {expected}")


def _validate_tool_external_action(work_order: WorkOrder, tool: dict[str, Any]) -> None:
    external_action_class = tool.get("external_action_class", "none")
    if external_action_class in {"none", "read"}:
        return
    policy = work_order.external_action_policy
    if policy.get("external_actions") == "none" or policy.get("publish_allowed") is False:
        raise WorkOrderValidationError(f"tool External Action is not allowed: {external_action_class}", "external_action_violation")


def _validate_external_action_report(work_order: WorkOrder, payload: dict[str, Any]) -> None:
    external_actions = payload.get("external_actions", [])
    if not external_actions:
        return
    policy = work_order.external_action_policy
    if policy.get("external_actions") == "none" or policy.get("publish_allowed") is False:
        raise WorkOrderValidationError("output reported unauthorized External Action", "external_action_violation")
