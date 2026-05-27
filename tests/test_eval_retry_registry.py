from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import (
    Artifact,
    EvalResult,
    FailureLearning,
    ImprovementProposal,
    MemoryWrite,
    ProcessRun,
    RegistryItem,
    RegistryKind,
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
        self.failure_learnings: list[FailureLearning] = []
        self.events: list[dict[str, Any]] = []
        self.registry_items = yaml_registry_items(Path("registries"))

    async def get_run_status(self, run_id: UUID) -> RunStatus:
        return self.run.status

    async def set_run_status(self, run_id: UUID, status: RunStatus, output: dict[str, Any] | None = None) -> None:
        self.run.status = status
        if output is not None:
            self.run.output = output

    async def get_run(self, run_id: UUID) -> dict[str, Any] | None:
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
            "failure_learnings": [learning.model_dump(mode="json") for learning in self.failure_learnings],
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

    async def record_failure_learnings(self, learnings: list[FailureLearning]) -> list[FailureLearning]:
        self.failure_learnings.extend(learnings)
        return learnings

    async def get_registry_item(self, kind: RegistryKind, key: str) -> RegistryItem | None:
        return next((item for item in self.registry_items if item.kind == kind and item.key == key), None)

    async def list_registry_items(self, kind: RegistryKind) -> list[RegistryItem]:
        return [item for item in self.registry_items if item.kind == kind]


class FakeMemory:
    async def write(self, write: MemoryWrite) -> None:
        pass


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
async def test_eval_threshold_overrides_worker_passed_flag_and_exposes_failure_context() -> None:
    run = ProcessRun(playbook_key="build-in-public", goal="judge drafts", status=RunStatus.CREATED, input={"require_human_approval": False})
    hermes = FakeHermes(
        [
            """
            {"action":"spawn_tasks","tasks":[
              {"task_type":"evaluate","worker_profile":"quality-judge","goal":"judge","inputs":{"drafts":[{"channel":"x","text":"ok","status":"published"}]},"artifact_type":"eval_report"}
            ]}
            """,
            '{"action":"fail","reason":"eval failed"}',
        ]
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).run_until_blocked_or_done(run.id)

    assert output["status"] == "failed"
    assert store.tasks[0].status == TaskStatus.FAILED
    assert store.evals[0].passed is False
    assert store.evals[0].checks["threshold"] == 0.75
    assert any(event["event_type"] == "task_eval_failed" for event in store.events)
    incident_events = [event for event in store.events if event["event_type"] == "incident_brief"]
    assert incident_events[0]["payload"]["failure_type"] == "eval_failed"


@pytest.mark.asyncio
async def test_retry_policy_retries_retryable_worker_failure_until_success() -> None:
    run = ProcessRun(playbook_key="build-in-public", goal="collect", status=RunStatus.CREATED, input={"require_human_approval": False})
    hermes = FakeHermes(
        [
            """
            {"action":"spawn_tasks","tasks":[
              {"task_type":"collect","worker_profile":"signal-collector","goal":"collect","inputs":{},"artifact_type":"signals"}
            ]}
            """,
            """
            {"action":"spawn_tasks","tasks":[
              {"task_type":"collect","worker_profile":"signal-collector","goal":"collect","inputs":{"signals":["ok"]},"artifact_type":"signals"}
            ]}
            """,
            '{"action":"finish","output":{"result":"done","memory_writes":[]}}',
        ]
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).run_until_blocked_or_done(run.id)

    assert output["status"] == "completed"
    assert len(store.tasks) == 2
    assert any(event["event_type"] == "incident_brief" for event in store.events)
    assert store.artifacts[0].payload["signals"][0]["text"] == "ok"
