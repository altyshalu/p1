from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import (
    Artifact,
    EvalResult,
    ImprovementProposal,
    MemoryWrite,
    ProcessRun,
    RegistryItem,
    RegistryKind,
    RunMode,
    RunStatus,
    TaskStatus,
    WorkOrder,
)
from l2l3_protocol.hub.registry import yaml_registry_items
from l2l3_protocol.memory.adapters import ProceduralRegistry
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.process_runtime import ProcessRuntime


class FakeStore:
    def __init__(self, run: ProcessRun) -> None:
        self.run = run
        self.tasks: list[WorkOrder] = []
        self.artifacts: list[Artifact] = []
        self.evals: list[EvalResult] = []
        self.improvement_proposals: list[ImprovementProposal] = []
        self.events: list[dict[str, Any]] = []
        self.registry_items = yaml_registry_items(Path("registries"))

    async def create_run(self, run: ProcessRun) -> ProcessRun:
        self.run = run
        return run

    async def get_run_status(self, run_id: UUID) -> RunStatus:
        return self.run.status

    async def set_run_status(self, run_id: UUID, status: RunStatus, output: dict[str, Any] | None = None) -> None:
        self.run.status = status
        if output is not None:
            self.run.output = output

    async def get_run(self, run_id: UUID) -> dict[str, Any] | None:
        if run_id != self.run.id:
            return None
        return {
            "id": str(self.run.id),
            "playbook_key": self.run.playbook_key,
            "l2_mode": self.run.l2_mode.value,
            "goal": self.run.goal,
            "status": self.run.status.value,
            "input": self.run.input,
            "output": self.run.output,
            "tasks": [task.model_dump(mode="json") for task in self.tasks],
            "artifacts": [
                {
                    "id": str(artifact.id),
                    "task_id": str(artifact.task_id) if artifact.task_id else None,
                    "artifact_type": artifact.artifact_type.value,
                    "payload": artifact.payload,
                }
                for artifact in self.artifacts
            ],
            "evals": [item.model_dump(mode="json") for item in self.evals],
            "events": self.events,
            "diagnosis": next((artifact.payload for artifact in reversed(self.artifacts) if artifact.artifact_type.value == "run_diagnosis"), None),
            "improvement_proposals": [proposal.model_dump(mode="json") for proposal in self.improvement_proposals],
        }

    async def add_task(self, work_order: WorkOrder) -> WorkOrder:
        self.tasks.append(work_order)
        return work_order

    async def set_task_status(self, task_id: UUID, status: TaskStatus) -> None:
        for task in self.tasks:
            if task.id == task_id:
                task.status = status

    async def add_artifact(self, artifact: Artifact) -> Artifact:
        self.artifacts.append(artifact)
        return artifact

    async def add_eval(self, eval_result: EvalResult) -> EvalResult:
        self.evals.append(eval_result)
        return eval_result

    async def add_event(self, run_id: UUID, event_type: str, payload: dict[str, Any], task_id: UUID | None = None) -> None:
        self.events.append({"event_type": event_type, "payload": payload, "task_id": str(task_id) if task_id else None})

    async def add_improvement_proposal(self, proposal: ImprovementProposal) -> ImprovementProposal:
        self.improvement_proposals.append(proposal)
        return proposal

    async def get_registry_item(self, kind: RegistryKind, key: str) -> RegistryItem | None:
        return next((item for item in self.registry_items if item.kind == kind and item.key == key), None)

    async def list_registry_items(self, kind: RegistryKind) -> list[RegistryItem]:
        return [item for item in self.registry_items if item.kind == kind]


class FakeMemory:
    def __init__(self) -> None:
        self.writes: list[MemoryWrite] = []

    async def write(self, write: MemoryWrite) -> None:
        self.writes.append(write)


class FakeHermes(HermesRuntime):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(Settings(hermes_enabled=True, deepseek_api_key="test"))
        self.responses = responses
        self.calls = 0

    def available(self) -> bool:
        return True

    async def run(self, prompt: str, system_message: str, task_id: str, enabled_toolsets: list[str] | None = None) -> str:
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


@pytest.mark.asyncio
async def test_runtime_executes_dynamic_l2_actions_without_fixed_stage_order() -> None:
    run = ProcessRun(
        playbook_key="build-in-public",
        goal="Share protocol progress",
        status=RunStatus.CREATED,
        input={
            "playbook_key": "build-in-public",
            "l2_mode": "execution",
            "goal": "Share protocol progress",
            "inputs": {"signals": ["Implemented generic runtime"], "channels": ["x"]},
            "require_human_approval": False,
        },
    )
    hermes = FakeHermes(
        [
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "collect_custom",
                  "worker_profile": "signal-collector",
                  "goal": "Normalize provided signals",
                  "inputs": {"signals": ["Implemented generic runtime"]},
                  "artifact_type": "signals"
                }
              ]
            }
            """,
            '{"action":"finish","output":{"result":"done","memory_writes":[]}}',
        ]
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).run_until_blocked_or_done(run.id)

    assert output["status"] == "completed"
    assert [task.task_type for task in store.tasks] == ["collect_custom"]
    assert store.artifacts[0].payload["signals"][0]["text"] == "Implemented generic runtime"


@pytest.mark.asyncio
async def test_runtime_records_worker_failure_without_synthetic_data() -> None:
    run = ProcessRun(playbook_key="build-in-public", goal="Share progress", status=RunStatus.CREATED, input={"require_human_approval": False})
    hermes = FakeHermes(
        [
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "collect",
                  "worker_profile": "signal-collector",
                  "goal": "Normalize provided signals",
                  "inputs": {},
                  "artifact_type": "signals"
                }
              ]
            }
            """,
            '{"action":"fail","reason":"Required signals are missing."}',
        ]
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).run_until_blocked_or_done(run.id)

    assert output["status"] == "failed"
    assert any(artifact.artifact_type.value == "run_diagnosis" for artifact in store.artifacts)
    assert store.improvement_proposals
    assert store.improvement_proposals[0].problem
    assert any(event["event_type"] == "task_failed" for event in store.events)


@pytest.mark.asyncio
async def test_runtime_can_resume_from_user_message() -> None:
    run = ProcessRun(playbook_key="build-in-public", goal="Share progress", status=RunStatus.WAITING_USER, input={"require_human_approval": False})
    hermes = FakeHermes(['{"action":"finish","output":{"result":"resumed","memory_writes":[]}}'])
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).resume_with_message(run.id, "Use these signals")

    assert output["status"] == "completed"
    assert any(event["event_type"] == "user_message" for event in store.events)


@pytest.mark.asyncio
async def test_design_mode_creates_playbook_proposal_without_work_orders() -> None:
    run = ProcessRun(
        playbook_key="weekly-research-synthesis",
        l2_mode=RunMode.DESIGN,
        goal="Design a weekly research synthesis Playbook",
        status=RunStatus.CREATED,
        input={"require_human_approval": True},
    )
    hermes = FakeHermes(
        [
            """
            {
              "playbook_key": "weekly-research-synthesis",
              "playbook_spec": {
                "key": "weekly-research-synthesis",
                "name": "Weekly Research Synthesis",
                "version": "0.1.0",
                "purpose": "Synthesize weekly research into reviewed internal notes.",
                "allowed_workers": ["signal-collector"],
                "allowed_tools": [],
                "required_inputs": ["sources"],
                "completion_criteria": ["summary is drafted"],
                "external_actions": {},
                "memory_policy": {"l3_direct_writes": false}
              },
              "required_workers": [],
              "required_tools": [],
              "required_evals": [],
              "registry_change_candidates": [
                {
                  "kind": "playbook",
                  "key": "weekly-research-synthesis",
                  "change_type": "create_spec",
                  "payload": {"key": "weekly-research-synthesis"},
                  "reason": "New requested workflow."
                }
              ],
              "test_plan": ["Run with a small real source list and verify summary output."],
              "risks": ["Needs a quality judge before publishing externally."],
              "approval_required": true
            }
            """
        ]
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).run_until_blocked_or_done(run.id)

    assert output["status"] == "waiting_approval"
    assert not store.tasks
    assert any(artifact.artifact_type.value == "playbook_proposal" for artifact in store.artifacts)
    assert any(event["event_type"] == "design_started" for event in store.events)
    assert any(event["event_type"] == "playbook_proposal_created" for event in store.events)
    assert any(event["event_type"] == "design_candidate_created" for event in store.events)


@pytest.mark.asyncio
async def test_execution_mode_fails_when_playbook_is_missing() -> None:
    run = ProcessRun(
        playbook_key="missing-playbook",
        l2_mode=RunMode.EXECUTION,
        goal="Run a missing Playbook",
        status=RunStatus.CREATED,
        input={"require_human_approval": False},
    )
    store = FakeStore(run)

    with pytest.raises(KeyError, match="Taskforce Hub playbook is not seeded"):
        await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), FakeHermes([])).run_until_blocked_or_done(run.id)
