from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from l2l3_protocol.core.schemas import L2SupervisorAction
from l2l3_protocol.runtime.hermes import HermesRuntime


ALLOWED_ACTIONS = {"spawn_tasks", "message_user", "finish", "fail", "propose_registry_change"}


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
                return self._parse_action(raw, process_pack, worker_profiles)
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
                    "If required inputs are missing, use message_user instead of inventing data.",
                    "For source collection tasks, pass real search parameters from state.input.inputs; do not ask the user for pre-collected source files.",
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
        cls._validate_action(action, process_pack, worker_profiles)
        return action

    @staticmethod
    def _validate_action(
        action: L2SupervisorAction,
        process_pack: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
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
        if action.action == "fail" and not action.reason:
            raise ValueError("fail action requires reason")
        for task in action.tasks:
            if task.worker_profile not in allowed_workers:
                raise ValueError(f"worker is not allowed by process pack: {task.worker_profile}")
            if task.worker_profile not in worker_profiles:
                raise ValueError(f"worker profile is not registered: {task.worker_profile}")
