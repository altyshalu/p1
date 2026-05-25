from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from l2l3_protocol.core.schemas import L2SupervisorAction
from l2l3_protocol.core.terminology import INCIDENT_BRIEF_EVENT, LEGACY_FAILURE_CONTEXT_EVENT
from l2l3_protocol.runtime.hermes import HermesRuntime


ALLOWED_ACTIONS = {"spawn_tasks", "message_user", "finish", "fail", "propose_registry_change"}
INTERNAL_REPAIR_FAILURE_TYPES = {
    "eval_failed",
    "output_schema",
    "invalid_json",
    "worker_exception",
    "timeout",
    "tool_denied",
    "side_effect_violation",
    "contract_validation",
}


class L2Supervisor:
    def __init__(self, hermes: HermesRuntime, max_repair_attempts: int = 2) -> None:
        self.hermes = hermes
        self.max_repair_attempts = max_repair_attempts

    async def next_action(
        self,
        playbook: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
        state: dict[str, Any],
        turn: int,
    ) -> L2SupervisorAction:
        if not self.hermes.available():
            raise RuntimeError("Hermes L2 supervisor is required but unavailable")
        prompt = self._prompt(playbook, worker_profiles, state, turn)
        system_message = (
            "You are the L2 supervisor for the L2 <-> L3 Communication Protocol. "
            "You manage execution through bounded L3 Work Orders. "
            "Return strict JSON only. Do not perform L3 work yourself."
        )
        raw = ""
        last_error: ValueError | None = None
        for attempt in range(self.max_repair_attempts + 1):
            raw = await self.hermes.run(
                prompt=prompt,
                system_message=system_message,
                task_id=f"l2-supervisor:{playbook['key']}:{turn}:{attempt}",
                enabled_toolsets=[],
            )
            try:
                return self._parse_action(raw, playbook, worker_profiles, state)
            except ValueError as exc:
                last_error = exc
                if attempt >= self.max_repair_attempts:
                    break
                prompt = self._repair_prompt(raw, str(exc), playbook, worker_profiles, state, turn)
        raise last_error or ValueError("Hermes L2 supervisor action failed validation")

    @staticmethod
    def _prompt(
        playbook: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
        state: dict[str, Any],
        turn: int,
    ) -> str:
        return json.dumps(
            {
                "instruction": "Choose the next bounded supervisor action for this run.",
                "turn": turn,
                "hard_constraints": [
                    "Return one JSON object and nothing else.",
                    "Allowed action values: spawn_tasks, message_user, finish, fail, propose_registry_change.",
                    "Use only allowed_workers from the Playbook.",
                    "Spawn at most max_tasks_per_turn tasks.",
                    "Humans own WHAT outcome matters; L2 owns HOW execution is repaired.",
                    "Use message_user only for missing user-owned outcome constraints, explicit approval, unsafe External Actions, spending/posting, or approval-required Taskforce Hub/executable behavior changes.",
                    "Never ask the user to approve internal repair mechanics: retries, worker respawn, rebriefs, schema field mapping, eval retry, provider query variants, threshold/debug analysis, or tool routing.",
                    "For internal failures such as eval_failed, output_schema, invalid_json, worker_exception, timeout, or tool_denied, autonomously choose spawn_tasks, propose_registry_change, or fail.",
                    "If the needed reusable repair capability does not exist, use propose_registry_change with a concrete reason and candidate spec; do not ask the user to design the worker/tool manually.",
                    "If required inputs are missing and they are factual/user-owned inputs, use message_user. If they can be inferred from artifacts, run input, or prior task outputs, repair autonomously.",
                    "For source collection tasks, pass real search parameters from state.input.inputs; do not ask the user for pre-collected source files.",
                    "When an Incident Brief includes repair_guidance, choose a protocol-safe repair: spawn a repaired Work Order with changed inputs, propose a Taskforce Hub/code change candidate, or fail explicitly. Ask the user only when the decision is truly product/editorial/safety-owned.",
                    "Do not silently drop a requested provider unless the repair policy explicitly allows partial continuation or the user approves it.",
                    "For provider_no_results, prefer multiple real provider-specific repair attempts before asking the user or failing.",
                    "If work is complete, use finish with final output.",
                    "If the run cannot continue, use fail with a reason.",
                ],
                "required_output_schema": {
                    "action": "spawn_tasks | message_user | finish | fail | propose_registry_change",
                    "message": "optional user-facing message",
                    "tasks": [
                        {
                            "task_type": "short stable task key",
                            "worker_profile": "registered worker key",
                            "goal": "bounded worker goal",
                            "inputs": {"key": "value"},
                        "artifact_type": "generic",
                        "allowed_tools": ["optional registered tool ids"],
                    }
                ],
                    "output": {"final": "object when action=finish"},
                    "reason": "required when action=fail",
                    "registry_change_candidate": {"optional": "candidate only"},
                },
                "playbook": playbook,
                "legacy_storage_note": "Internal persisted kind may still be process_pack and task contracts; public terms are Playbook and Work Order.",
                "worker_capabilities": {
                    key: {
                        "description": profile.get("description"),
                        "worker_type": profile.get("worker_type"),
                        "input_schema": profile.get("input_schema", {}),
                        "output_schema": profile.get("output_schema", {}),
                        "retry_policy": profile.get("retry_policy", {}),
                        "repair_strategy": profile.get("repair_strategy", {}),
                        "external_action_policy": profile.get("side_effect_policy", {}),
                        "side_effect_policy": profile.get("side_effect_policy", {}),
                    }
                    for key, profile in worker_profiles.items()
                },
                "state": state,
            },
            ensure_ascii=True,
        )

    @staticmethod
    def _repair_prompt(
        previous_output: str,
        validation_error: str,
        playbook: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
        state: dict[str, Any],
        turn: int,
    ) -> str:
        return json.dumps(
            {
                "instruction": "Repair the previous L2 supervisor action so it passes validation.",
                "validation_error": validation_error,
                "previous_output": previous_output,
                "allowed_actions": sorted(ALLOWED_ACTIONS),
                "allowed_workers": playbook.get("allowed_workers", []),
                "max_tasks_per_turn": playbook.get("max_tasks_per_turn", 3),
                "worker_keys": sorted(worker_profiles),
                "state": state,
                "turn": turn,
            },
            ensure_ascii=True,
        )

    @classmethod
    def _parse_action(
        cls,
        raw: str,
        playbook: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
        state: dict[str, Any],
    ) -> L2SupervisorAction:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError("Hermes L2 action is not valid JSON")
            data = json.loads(match.group(0))
        try:
            action = L2SupervisorAction.model_validate(data)
        except ValidationError as exc:
            raise ValueError("Hermes L2 action does not match the required schema") from exc
        cls._validate_action(action, playbook, worker_profiles, state)
        return action

    @staticmethod
    def _validate_action(
        action: L2SupervisorAction,
        playbook: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
        state: dict[str, Any],
    ) -> None:
        if action.action not in ALLOWED_ACTIONS:
            raise ValueError(f"unknown L2 action: {action.action}")
        allowed_workers = set(playbook.get("allowed_workers", []))
        if not allowed_workers:
            raise ValueError("Playbook must define allowed_workers")
        max_tasks = int(playbook.get("max_tasks_per_turn", 3))
        if len(action.tasks) > max_tasks:
            raise ValueError(f"L2 spawned too many tasks: {len(action.tasks)} > {max_tasks}")
        if action.action == "spawn_tasks" and not action.tasks:
            raise ValueError("spawn_tasks action requires at least one task")
        if action.action != "spawn_tasks" and action.tasks:
            raise ValueError(f"{action.action} action must not include tasks")
        if action.action == "finish" and not _required_evals_passed(playbook, state):
            raise ValueError("finish is not allowed until required evals pass")
        if action.action == "message_user" and not action.message:
            raise ValueError("message_user action requires message")
        if action.action == "message_user" and not _message_user_allowed(state):
            raise ValueError(
                "message_user is not allowed for internal L2 repair mechanics; choose spawn_tasks, propose_registry_change, or fail"
            )
        if action.action == "fail" and not action.reason:
            raise ValueError("fail action requires reason")
        for task in action.tasks:
            if task.worker_profile not in allowed_workers:
                raise ValueError(f"worker is not allowed by Playbook: {task.worker_profile}")
            if task.worker_profile not in worker_profiles:
                raise ValueError(f"worker profile is not registered: {task.worker_profile}")
            if task.worker_profile == "approval-adapter" and not _required_evals_passed(playbook, state):
                raise ValueError("approval-adapter is not allowed until required evals pass")


def _message_user_allowed(state: dict[str, Any]) -> bool:
    latest_failure = _latest_task_failure_context(state)
    if latest_failure is None:
        return True
    failure_type = str(latest_failure.get("failure_type", ""))
    if failure_type in INTERNAL_REPAIR_FAILURE_TYPES:
        return False
    return True


def _latest_task_failure_context(state: dict[str, Any]) -> dict[str, Any] | None:
    for event in reversed(state.get("events", [])):
        if event.get("event_type") not in {INCIDENT_BRIEF_EVENT, LEGACY_FAILURE_CONTEXT_EVENT}:
            continue
        payload = event.get("payload", {})
        return payload if isinstance(payload, dict) else None
    return None


def _required_evals_passed(process_pack: dict[str, Any], state: dict[str, Any]) -> bool:
    required_eval_keys = process_pack.get("required_eval_keys", [])
    if not required_eval_keys:
        return True
    latest_by_key: dict[str, dict[str, Any]] = {}
    for eval_result in state.get("evals", []):
        eval_key = eval_result.get("eval_key")
        if eval_key:
            latest_by_key[str(eval_key)] = eval_result
    return all(bool(latest_by_key.get(str(eval_key), {}).get("passed")) for eval_key in required_eval_keys)
