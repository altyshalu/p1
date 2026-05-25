from __future__ import annotations

from l2l3_protocol.core.schemas import RegistryKind


TASKFORCE_HUB = "Taskforce Hub"
PLAYBOOK = "Playbook"
WORK_ORDER = "Work Order"
EXTERNAL_ACTIONS = "External Actions"
INCIDENT_BRIEF = "Incident Brief"
RUNTIME = "Runtime"

INCIDENT_BRIEF_EVENT = "incident_brief"
LEGACY_FAILURE_CONTEXT_EVENT = "task_failure_context"

HUB_KIND_ALIASES = {
    "tool": RegistryKind.TOOL,
    "tools": RegistryKind.TOOL,
    "worker": RegistryKind.WORKER,
    "workers": RegistryKind.WORKER,
    "eval": RegistryKind.EVAL,
    "evals": RegistryKind.EVAL,
    "playbook": RegistryKind.PROCESS_PACK,
    "playbooks": RegistryKind.PROCESS_PACK,
    "process_pack": RegistryKind.PROCESS_PACK,
    "process_packs": RegistryKind.PROCESS_PACK,
    "failure_pattern": RegistryKind.FAILURE_PATTERN,
    "failure_patterns": RegistryKind.FAILURE_PATTERN,
}


def normalize_hub_kind(value: str) -> RegistryKind:
    key = value.strip().lower().replace("-", "_")
    if key in HUB_KIND_ALIASES:
        return HUB_KIND_ALIASES[key]
    return RegistryKind(key)


def display_event_type(event_type: str) -> str:
    if event_type == LEGACY_FAILURE_CONTEXT_EVENT:
        return INCIDENT_BRIEF_EVENT
    return event_type
