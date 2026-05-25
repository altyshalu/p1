from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import Artifact, EvalResult, MemoryWrite, ProcessRun, RegistryItem, RegistryKind, RunStatus, TaskContract, TaskStatus
from l2l3_protocol.marketplace.registry import yaml_registry_items
from l2l3_protocol.memory.adapters import ProceduralRegistry
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.process_runtime import ProcessRuntime


class FakeStore:
    def __init__(self, run: ProcessRun) -> None:
        self.run = run
        self.tasks: list[TaskContract] = []
        self.artifacts: list[Artifact] = []
        self.evals: list[EvalResult] = []
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
            "process_key": self.run.process_key,
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
        }

    async def add_task(self, contract: TaskContract) -> TaskContract:
        self.tasks.append(contract)
        return contract

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
        process_key="build-in-public",
        goal="Share protocol progress",
        status=RunStatus.CREATED,
        input={
            "process_key": "build-in-public",
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
    run = ProcessRun(process_key="build-in-public", goal="Share progress", status=RunStatus.CREATED, input={"require_human_approval": False})
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
    assert not store.artifacts
    assert any(event["event_type"] == "task_failed" for event in store.events)


@pytest.mark.asyncio
async def test_runtime_can_resume_from_user_message() -> None:
    run = ProcessRun(process_key="build-in-public", goal="Share progress", status=RunStatus.WAITING_USER, input={"require_human_approval": False})
    hermes = FakeHermes(['{"action":"finish","output":{"result":"resumed","memory_writes":[]}}'])
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).resume_with_message(run.id, "Use these signals")

    assert output["status"] == "completed"
    assert any(event["event_type"] == "user_message" for event in store.events)
