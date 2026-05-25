from __future__ import annotations

from l2l3_protocol.core.schemas import RegistryKind


TASKFORCE_HUB = "Taskforce Hub"
PLAYBOOK = "Playbook"
WORK_ORDER = "Work Order"
EXTERNAL_ACTIONS = "External Actions"
INCIDENT_BRIEF = "Incident Brief"
RUNTIME = "Runtime"

INCIDENT_BRIEF_EVENT = "incident_brief"

HUB_KIND_ALIASES = {
    "tool": RegistryKind.TOOL,
    "tools": RegistryKind.TOOL,
    "worker": RegistryKind.WORKER,
    "workers": RegistryKind.WORKER,
    "eval": RegistryKind.EVAL,
    "evals": RegistryKind.EVAL,
    "playbook": RegistryKind.PLAYBOOK,
    "playbooks": RegistryKind.PLAYBOOK,
    "failure_pattern": RegistryKind.FAILURE_PATTERN,
    "failure_patterns": RegistryKind.FAILURE_PATTERN,
}


def normalize_hub_kind(value: str) -> RegistryKind:
    key = value.strip().lower().replace("-", "_")
    if key in HUB_KIND_ALIASES:
        return HUB_KIND_ALIASES[key]
    return RegistryKind(key)


def display_event_type(event_type: str) -> str:
    return event_type
