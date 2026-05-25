from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from l2l3_protocol.core.schemas import L2DesignProposal
from l2l3_protocol.runtime.hermes import HermesRuntime


class L2DesignController:
    def __init__(self, hermes: HermesRuntime, max_repair_attempts: int = 2) -> None:
        self.hermes = hermes
        self.max_repair_attempts = max_repair_attempts

    async def propose_playbook(self, state: dict[str, Any], hub_snapshot: dict[str, Any]) -> L2DesignProposal:
        if not self.hermes.available():
            raise RuntimeError("Hermes L2 Design Controller is required but unavailable")
        prompt = self._prompt(state, hub_snapshot)
        system_message = (
            "You are the L2 Design Controller for the L2 <-> L3 Active Inference Runtime. "
            "Design a Playbook proposal only. Do not execute work, mutate Taskforce Hub, or perform External Actions. "
            "Return strict JSON only."
        )
        raw = ""
        last_error: ValueError | None = None
        for attempt in range(self.max_repair_attempts + 1):
            raw = await self.hermes.run(
                prompt=prompt,
                system_message=system_message,
                task_id=f"l2-design:{state['id']}:{attempt}",
                enabled_toolsets=[],
            )
            try:
                return self._parse_proposal(raw)
            except ValueError as exc:
                last_error = exc
                if attempt >= self.max_repair_attempts:
                    break
                prompt = self._repair_prompt(raw, str(exc), state, hub_snapshot)
        raise last_error or ValueError("Hermes L2 Design proposal failed validation")

    @staticmethod
    def _prompt(state: dict[str, Any], hub_snapshot: dict[str, Any]) -> str:
        return json.dumps(
            {
                "instruction": "Design a new or changed Playbook proposal for this run.",
                "hard_constraints": [
                    "Return one JSON object and nothing else.",
                    "Do not execute the Playbook.",
                    "Do not mutate Taskforce Hub directly.",
                    "Every executable or policy-changing registry change must be represented as a candidate and require approval.",
                    "Use only real Hub facts from hub_snapshot; if a worker/tool/eval does not exist, propose it as a candidate.",
                    "The proposal must include a concrete test_plan.",
                    "approval_required must be true.",
                ],
                "required_output_schema": {
                    "playbook_key": "stable kebab-case key",
                    "playbook_spec": {
                        "key": "same as playbook_key",
                        "name": "human-readable name",
                        "version": "0.1.0",
                        "purpose": "bounded purpose",
                        "allowed_workers": [],
                        "allowed_tools": [],
                        "required_inputs": [],
                        "completion_criteria": [],
                        "external_actions": {},
                        "memory_policy": {},
                    },
                    "required_workers": [],
                    "required_tools": [],
                    "required_evals": [],
                    "registry_change_candidates": [],
                    "test_plan": [],
                    "risks": [],
                    "approval_required": True,
                },
                "state": state,
                "hub_snapshot": hub_snapshot,
            },
            ensure_ascii=True,
        )

    @staticmethod
    def _repair_prompt(previous_output: str, validation_error: str, state: dict[str, Any], hub_snapshot: dict[str, Any]) -> str:
        return json.dumps(
            {
                "instruction": "Repair the previous L2 Design proposal so it passes validation.",
                "validation_error": validation_error,
                "previous_output": previous_output,
                "state": state,
                "hub_snapshot": hub_snapshot,
            },
            ensure_ascii=True,
        )

    @classmethod
    def _parse_proposal(cls, raw: str) -> L2DesignProposal:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError:
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not match:
                raise ValueError("Hermes L2 Design proposal is not valid JSON")
            data = json.loads(match.group(0))
        try:
            proposal = L2DesignProposal.model_validate(data)
        except ValidationError as exc:
            raise ValueError("Hermes L2 Design proposal does not match the required schema") from exc
        cls._validate_proposal(proposal)
        return proposal

    @staticmethod
    def _validate_proposal(proposal: L2DesignProposal) -> None:
        if proposal.playbook_spec.get("key") != proposal.playbook_key:
            raise ValueError("playbook_spec.key must match playbook_key")
        if proposal.approval_required is not True:
            raise ValueError("Design Mode proposals must require approval")
        for key in ["allowed_workers", "allowed_tools", "required_inputs", "completion_criteria", "external_actions"]:
            if key not in proposal.playbook_spec:
                raise ValueError(f"playbook_spec missing required field: {key}")
        if not proposal.test_plan:
            raise ValueError("Design Mode proposal must include a test_plan")
