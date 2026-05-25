from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from l2l3_protocol.core.schemas import L2SupervisorAction
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
        process_pack: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
        state: dict[str, Any],
        turn: int,
    ) -> L2SupervisorAction:
        if not self.hermes.available():
            raise RuntimeError("Hermes L2 supervisor is required but unavailable")
        prompt = self._prompt(process_pack, worker_profiles, state, turn)
        system_message = (
            "You are the L2 supervisor for the L2 <-> L3 Communication Protocol. "
            "You manage execution through bounded L3 worker contracts. "
            "Return strict JSON only. Do not perform L3 work yourself."
        )
        raw = ""
        last_error: ValueError | None = None
        for attempt in range(self.max_repair_attempts + 1):
            raw = await self.hermes.run(
                prompt=prompt,
                system_message=system_message,
                task_id=f"l2-supervisor:{process_pack['key']}:{turn}:{attempt}",
                enabled_toolsets=[],
            )
            try:
                return self._parse_action(raw, process_pack, worker_profiles, state)
            except ValueError as exc:
                last_error = exc
                if attempt >= self.max_repair_attempts:
                    break
                prompt = self._repair_prompt(raw, str(exc), process_pack, worker_profiles, state, turn)
        raise last_error or ValueError("Hermes L2 supervisor action failed validation")

    @staticmethod
    def _prompt(
        process_pack: dict[str, Any],
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
                    "Use only allowed_workers from the process pack.",
                    "Spawn at most max_tasks_per_turn tasks.",
                    "Humans own WHAT outcome matters; L2 owns HOW execution is repaired.",
                    "Use message_user only for missing user-owned outcome constraints, explicit approval, unsafe/external side effects, spending/posting, or approval-required registry/executable behavior changes.",
                    "Never ask the user to approve internal repair mechanics: retries, worker respawn, rebriefs, schema field mapping, eval retry, provider query variants, threshold/debug analysis, or tool routing.",
                    "For internal failures such as eval_failed, output_schema, invalid_json, worker_exception, timeout, or tool_denied, autonomously choose spawn_tasks, propose_registry_change, or fail.",
                    "If required inputs are missing and they are factual/user-owned inputs, use message_user. If they can be inferred from artifacts, run input, or prior task outputs, repair autonomously.",
                    "For source collection tasks, pass real search parameters from state.input.inputs; do not ask the user for pre-collected source files.",
                    "When a task_failure_context includes repair_guidance, choose a protocol-safe repair: spawn a repaired task with changed inputs, propose a registry/code change candidate, or fail explicitly. Ask the user only when the decision is truly product/editorial/safety-owned.",
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
                "process_pack": process_pack,
                "worker_capabilities": {
                    key: {
                        "description": profile.get("description"),
                        "worker_type": profile.get("worker_type"),
                        "input_schema": profile.get("input_schema", {}),
                        "output_schema": profile.get("output_schema", {}),
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
        process_pack: dict[str, Any],
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
                "allowed_workers": process_pack.get("allowed_workers", []),
                "max_tasks_per_turn": process_pack.get("max_tasks_per_turn", 3),
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
        process_pack: dict[str, Any],
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
        cls._validate_action(action, process_pack, worker_profiles, state)
        return action

    @staticmethod
    def _validate_action(
        action: L2SupervisorAction,
        process_pack: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
        state: dict[str, Any],
    ) -> None:
        if action.action not in ALLOWED_ACTIONS:
            raise ValueError(f"unknown L2 action: {action.action}")
        allowed_workers = set(process_pack.get("allowed_workers", []))
        if not allowed_workers:
            raise ValueError("process pack must define allowed_workers")
        max_tasks = int(process_pack.get("max_tasks_per_turn", 3))
        if len(action.tasks) > max_tasks:
            raise ValueError(f"L2 spawned too many tasks: {len(action.tasks)} > {max_tasks}")
        if action.action == "spawn_tasks" and not action.tasks:
            raise ValueError("spawn_tasks action requires at least one task")
        if action.action != "spawn_tasks" and action.tasks:
            raise ValueError(f"{action.action} action must not include tasks")
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
                raise ValueError(f"worker is not allowed by process pack: {task.worker_profile}")
            if task.worker_profile not in worker_profiles:
                raise ValueError(f"worker profile is not registered: {task.worker_profile}")


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
        if event.get("event_type") != "task_failure_context":
            continue
        payload = event.get("payload", {})
        return payload if isinstance(payload, dict) else None
    return None
