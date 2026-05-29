from pathlib import Path
import json
from typing import Any
from uuid import UUID

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import Artifact, EvalResult, FailureLearning, ImprovementProposal, ImprovementProposalStatus, MemoryWrite, ProcessRun, RegistryItem, RegistryKind, RunStatus, TaskStatus, WorkOrder
from l2l3_protocol.hub.registry import yaml_registry_items
from l2l3_protocol.memory.adapters import ProceduralRegistry
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.process_runtime import ProcessRuntime
from l2l3_protocol.workers.build_in_public_worker import claim_grounding, normalize_draft_schema, stop_slop_edit, trend_quality


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

    async def add_improvement_proposal(self, proposal: ImprovementProposal) -> ImprovementProposal:
        self.improvement_proposals.append(proposal)
        return proposal

    async def list_improvement_proposals(
        self,
        status: ImprovementProposalStatus | None = None,
        run_id: UUID | None = None,
    ) -> list[ImprovementProposal]:
        proposals = self.improvement_proposals
        if status is not None:
            proposals = [proposal for proposal in proposals if proposal.status == status]
        if run_id is not None:
            proposals = [proposal for proposal in proposals if proposal.run_id == run_id]
        return proposals

    async def record_failure_learnings(self, learnings: list[FailureLearning]) -> list[FailureLearning]:
        self.failure_learnings.extend(learnings)
        return learnings

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


def test_draft_schema_normalizer_repairs_eval_shapes_and_source_formatting() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "source_format": "separate_section",
                "drafts": [
                    {
                        "channel": "x",
                        "thread": ["Claim text https://example.com/a"],
                        "claims": [{"text": "Claim text", "evidence_urls": ["https://example.com/a"]}],
                    }
                ],
            }
        },
        {},
    )

    draft = payload["drafts"][0]

    assert draft["text"].endswith("Sources:\n- https://example.com/a")
    assert draft["claims"][0]["source_url"] == "https://example.com/a"
    assert draft["publish"] is False
    assert draft["status"] == "draft"
    assert claim_grounding({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True
    assert trend_quality({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True


def test_draft_schema_normalizer_derives_claims_from_explicit_sources_without_inventing_evidence() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "drafts": [
                    {
                        "channel": "x",
                        "text": "Agent runtimes need typed work orders. Source: https://example.com/runtime",
                    }
                ]
            }
        },
        {},
    )

    draft = payload["drafts"][0]

    assert draft["sources"] == ["https://example.com/runtime"]
    assert draft["claims"] == [
        {
            "text": "Agent runtimes need typed work orders. Source: https://example.com/runtime",
            "source_url": "https://example.com/runtime",
            "evidence_urls": ["https://example.com/runtime"],
        }
    ]
    assert claim_grounding({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True


def test_draft_schema_normalizer_maps_body_to_text_for_real_draft_writer_contract() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "drafts": [
                    {
                        "channel": "x",
                        "body": "openai/codex is a terminal coding agent. https://github.com/openai/codex",
                        "source_urls": ["https://github.com/openai/codex"],
                    }
                ]
            }
        },
        {},
    )

    draft = payload["drafts"][0]

    assert draft["text"].startswith("openai/codex is a terminal coding agent")
    assert draft["claims"][0]["source_url"] == "https://github.com/openai/codex"
    assert stop_slop_edit({"inputs": {"drafts": payload["drafts"]}}, {})["edited_drafts"][0]["text"]
    assert claim_grounding({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True


def test_draft_schema_normalizer_maps_draft_text_from_real_writer_contract() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "drafts": [
                    {
                        "channel": "x",
                        "draft_text": "ECC supports agent memory workflows. https://github.com/affaan-m/ECC",
                        "claims": [
                            {
                                "statement": "ECC supports agent memory workflows.",
                                "source_url": "https://github.com/affaan-m/ECC",
                            }
                        ],
                    }
                ]
            }
        },
        {},
    )

    draft = payload["drafts"][0]

    assert draft["text"].startswith("ECC supports agent memory workflows.")
    assert draft["claims"][0]["text"] == "ECC supports agent memory workflows."
    assert stop_slop_edit({"inputs": {"drafts": payload["drafts"]}}, {})["edited_drafts"][0]["text"]


def test_draft_schema_normalizer_maps_claim_text_to_eval_text() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "drafts": [
                    {
                        "channel": "x",
                        "text": "1/ AgentBase ships traces and replay. https://github.com/shenyangs/AgentBase",
                        "claims": [
                            {
                                "id": "atom-2",
                                "claim_text": "AgentBase ships traces and replay.",
                                "source_url": "https://github.com/shenyangs/AgentBase",
                            }
                        ],
                    }
                ]
            }
        },
        {},
    )

    claim = payload["drafts"][0]["claims"][0]

    assert claim["text"] == "AgentBase ships traces and replay."
    assert claim["source_url"] == "https://github.com/shenyangs/AgentBase"
    assert claim_grounding({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True


def test_draft_schema_normalizer_injects_channel_from_real_run_inputs() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "channels": ["x"],
                "drafts": [
                    {
                        "text": "AgentBase is a local-first TypeScript agent runtime. https://github.com/shenyangs/AgentBase",
                        "claims": [
                            {
                                "text": "AgentBase is a local-first TypeScript agent runtime.",
                                "source_url": "https://github.com/shenyangs/AgentBase",
                            }
                        ],
                    }
                ],
            }
        },
        {},
    )

    draft = payload["drafts"][0]

    assert draft["channel"] == "x"
    assert trend_quality({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True


def test_draft_schema_normalizer_injects_channel_from_run_context_for_repair_tasks() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "drafts": [
                    {
                        "text": "AgentBase is a local-first TypeScript agent runtime. https://github.com/shenyangs/AgentBase",
                        "status": "draft",
                        "publish": False,
                    }
                ],
            }
        },
        {"input": {"channel": "x"}},
    )

    draft = payload["drafts"][0]

    assert draft["channel"] == "x"
    assert trend_quality({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True


def test_draft_schema_normalizer_accepts_string_drafts_from_repair_path() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "channel": "x",
                "drafts": ["AgentBase is a local-first runtime. https://github.com/shenyangs/AgentBase"],
            }
        },
        {},
    )

    draft = payload["drafts"][0]

    assert draft["text"].startswith("AgentBase is a local-first runtime.")
    assert draft["channel"] == "x"
    assert draft["claims"][0]["source_url"] == "https://github.com/shenyangs/AgentBase"


def test_draft_schema_normalizer_derives_thread_claim_text_from_thread_item_without_repr() -> None:
    payload = normalize_draft_schema(
        {
            "inputs": {
                "drafts": [
                    {
                        "channel": "x",
                        "thread": [
                            {
                                "text": "1/ MUSE-Autoskill uses skill-level memory. arxiv.org/abs/2605.27366",
                                "claims": [{"id": "atom-6", "source_url": "http://arxiv.org/abs/2605.27366v1"}],
                            }
                        ],
                    }
                ]
            }
        },
        {},
    )

    draft = payload["drafts"][0]

    assert "{'text':" not in draft["text"]
    assert draft["claims"] == [
        {
            "id": "atom-6",
            "source_url": "http://arxiv.org/abs/2605.27366v1",
            "text": "1/ MUSE-Autoskill uses skill-level memory. arxiv.org/abs/2605.27366",
        }
    ]
    assert draft["sources"] == ["http://arxiv.org/abs/2605.27366v1"]
    assert claim_grounding({"inputs": {"drafts": payload["drafts"]}}, {})["passed"] is True


def test_stop_slop_editor_accepts_thread_drafts_without_user_mapping() -> None:
    payload = stop_slop_edit({"inputs": {"drafts": [{"channel": "x", "thread": ["A game-changing update."], "sources": []}]}}, {})

    assert payload["edited_drafts"][0]["text"] == "A update."


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
                            "claim": "Agent runtimes need typed work_orders and eval gates.",
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
                                        "claim": "Agent runtimes need typed work_orders and eval gates.",
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
        playbook_key="build-in-public-trend-radar",
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
