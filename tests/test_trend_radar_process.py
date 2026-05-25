from pathlib import Path
import json
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

    async def get_run_status(self, run_id: UUID) -> RunStatus:
        return self.run.status

    async def set_run_status(self, run_id: UUID, status: RunStatus, output: dict[str, Any] | None = None) -> None:
        self.run.status = status
        if output is not None:
            self.run.output = output

    async def get_run(self, run_id: UUID) -> dict[str, Any] | None:
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
        response = self.responses[self.calls]
        self.calls += 1
        return response


def trend_sources() -> list[dict[str, Any]]:
    return [
        {
            "source": "github",
            "items": [
                {
                    "title": "openai-codex",
                    "url": "https://github.com/openai/codex",
                    "summary": "A runtime for typed agent evals and worker orchestration.",
                    "metrics": {"stars": 420},
                }
            ],
        },
    ]


@pytest.mark.asyncio
async def test_trend_radar_process_exercises_tools_agentic_workers_evals_and_approval() -> None:
    sources = trend_sources()
    trend_signals = [
        {
            "source": item_group["source"],
            "title": item["title"],
            "url": item["url"],
            "summary": item["summary"],
            "metrics": item["metrics"],
        }
        for item_group in sources
        for item in item_group["items"]
    ]
    ranked_signals = [{**signal, "score": 0.9, "reasons": ["agent orchestration relevance"]} for signal in trend_signals]
    drafts = [
        {
            "channel": "x",
            "status": "draft",
            "text": "We are testing ABRT against real trend-radar work: source collection, ranking, drafting, editing, and eval gates.",
            "claims": [
                {
                    "text": "ABRT is testing source collection, ranking, drafting, editing, and eval gates.",
                    "source_url": "https://github.com/openai/codex",
                }
            ],
        }
    ]
    hermes = FakeHermes(
        [
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "collect_trend_sources",
                            "worker_profile": "trend-source-collector",
                            "goal": "Collect real trend sources",
                            "inputs": {"query": "openai codex", "providers": ["github"], "max_results": 1},
                            "artifact_type": "signals",
                            "allowed_tools": ["github-search-tool"],
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "deduplicate_trends",
                            "worker_profile": "trend-deduplicator",
                            "goal": "Deduplicate trend signals",
                            "inputs": {"trend_signals": trend_signals},
                            "artifact_type": "signals",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "score_relevance",
                            "worker_profile": "relevance-scorer",
                            "goal": "Rank trend relevance",
                            "inputs": {"deduped_signals": trend_signals, "themes": ["L2", "L3", "agent", "eval", "worker"]},
                            "artifact_type": "signals",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "strategize_trends",
                            "worker_profile": "trend-narrative-strategist",
                            "goal": "Create narrative atoms",
                            "inputs": {"ranked_signals": ranked_signals},
                            "artifact_type": "content_atoms",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "content_atoms": [
                        {
                            "angle": "trend_radar",
                            "claim": "Agent runtimes need typed contracts and eval gates.",
                            "why_it_matters": "This is the exact operating model ABRT is building.",
                            "evidence": ["https://github.com/openai/codex"],
                        }
                    ]
                }
            ),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "write_trend_drafts",
                            "worker_profile": "trend-draft-writer",
                            "goal": "Write channel drafts",
                            "inputs": {
                                "content_atoms": [
                                    {
                                        "angle": "trend_radar",
                                        "claim": "Agent runtimes need typed contracts and eval gates.",
                                        "why_it_matters": "This is the exact operating model ABRT is building.",
                                        "evidence": ["https://github.com/openai/codex"],
                                    }
                                ],
                                "channels": ["x"],
                            },
                            "artifact_type": "channel_drafts",
                        }
                    ],
                }
            ),
            json.dumps({"drafts": drafts}),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "stop_slop_edit",
                            "worker_profile": "stop-slop-editor",
                            "goal": "Remove AI writing tells",
                            "inputs": {"drafts": drafts},
                            "artifact_type": "channel_drafts",
                            "allowed_tools": ["stop-slop-editor-tool"],
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "claim_grounding",
                            "worker_profile": "claim-grounding-judge",
                            "goal": "Check claim grounding",
                            "inputs": {"drafts": drafts},
                            "artifact_type": "eval_report",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "trend_quality",
                            "worker_profile": "trend-draft-quality-judge",
                            "goal": "Check draft quality",
                            "inputs": {"drafts": drafts},
                            "artifact_type": "eval_report",
                        }
                    ],
                }
            ),
            json.dumps(
                {
                    "action": "spawn_tasks",
                    "tasks": [
                        {
                            "task_type": "approve",
                            "worker_profile": "approval-adapter",
                            "goal": "Record approval gate",
                            "inputs": {"require_human_approval": True},
                            "artifact_type": "approval_decision",
                        }
                    ],
                }
            ),
            json.dumps({"action": "finish", "output": {"result": "trend radar draft ready for human review", "memory_writes": []}}),
        ]
    )
    run = ProcessRun(
        process_key="build-in-public-trend-radar",
        goal="Find AI/dev trends and produce reviewed build-in-public draft",
        status=RunStatus.CREATED,
        input={"require_human_approval": True},
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), hermes).run_until_blocked_or_done(run.id)

    assert output["status"] == "waiting_approval"
    assert [task.worker_profile for task in store.tasks] == [
        "trend-source-collector",
        "trend-deduplicator",
        "relevance-scorer",
        "trend-narrative-strategist",
        "trend-draft-writer",
        "stop-slop-editor",
        "claim-grounding-judge",
        "trend-draft-quality-judge",
        "approval-adapter",
    ]
    assert all(eval_result.passed for eval_result in store.evals)
    assert {eval_result.eval_key for eval_result in store.evals} == {"trend-claim-grounding", "trend-draft-quality"}
    assert any(artifact.payload.get("edited_drafts") for artifact in store.artifacts)
