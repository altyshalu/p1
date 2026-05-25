from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from l2l3_protocol.core.schemas import RegistryChangeCandidateCreate, RegistryChangeStatus, RegistryItem, RegistryKind


SAFE_CHANGE_TYPES = {"update_metadata", "update_stats", "record_health"}
SAFE_KINDS = {RegistryKind.EVAL, RegistryKind.FAILURE_PATTERN, RegistryKind.WORKER}
UNSAFE_SPEC_KEYS = {
    "allowed_tools",
    "auth",
    "auth_requirements",
    "budget",
    "entrypoint",
    "executable",
    "input_schema",
    "output_schema",
    "process",
    "retry_policy",
    "external_action_class",
    "external_action_policy",
    "toolset",
    "worker_type",
}


def is_safe_registry_change(candidate: RegistryChangeCandidateCreate) -> bool:
    if candidate.change_type not in SAFE_CHANGE_TYPES or candidate.kind not in SAFE_KINDS:
        return False
    return not bool(UNSAFE_SPEC_KEYS.intersection(candidate.payload))


def apply_registry_change(item: RegistryItem | None, candidate: RegistryChangeCandidateCreate) -> RegistryItem:
    if item is None:
        item = RegistryItem(kind=candidate.kind, key=candidate.key, spec={})
    if candidate.change_type in SAFE_CHANGE_TYPES:
        item.metadata = {**item.metadata, **candidate.payload}
        return item
    item.spec = {**item.spec, **candidate.payload}
    return item


def yaml_registry_items(root: Path) -> list[RegistryItem]:
    items: list[RegistryItem] = []
    items.extend(_load_dir(root / "worker-profiles", RegistryKind.WORKER))
    items.extend(_load_dir(root / "evals", RegistryKind.EVAL))
    for path in sorted((root / "playbooks").glob("*/playbook.yaml")):
        spec = _load_yaml(path)
        items.append(_item_from_spec(RegistryKind.PLAYBOOK, spec))
    tools_dir = root / "tools"
    if tools_dir.exists():
        for path in sorted(tools_dir.glob("*.yaml")):
            spec = _load_yaml(path)
            items.append(_item_from_spec(RegistryKind.TOOL, spec))
    patterns_dir = root / "failure-patterns"
    if patterns_dir.exists():
        for path in sorted(patterns_dir.glob("*.yaml")):
            spec = _load_yaml(path)
            items.append(_item_from_spec(RegistryKind.FAILURE_PATTERN, spec))
    return items


def _load_dir(path: Path, kind: RegistryKind) -> list[RegistryItem]:
    if not path.exists():
        return []
    return [_item_from_spec(kind, _load_yaml(item_path)) for item_path in sorted(path.glob("*.yaml"))]


def _item_from_spec(kind: RegistryKind, spec: dict[str, Any]) -> RegistryItem:
    key = spec.get("key") or spec.get("eval_id") or spec.get("pattern_id") or spec.get("tool_id")
    if not key:
        raise ValueError(f"registry {kind.value} item is missing explicit key")
    return RegistryItem(kind=kind, key=key, version=str(spec.get("version", "0.1.0")), spec=spec)


def _load_yaml(path: Path) -> dict[str, Any]:
    loaded = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(loaded, dict) or not loaded:
        raise ValueError(f"registry YAML is empty or invalid: {path}")
    return loaded
