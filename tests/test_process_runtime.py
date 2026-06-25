from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import (
    Artifact,
    ArtifactType,
    EvalResult,
    FailureLearning,
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
from l2l3_protocol.runtime.l3_executor import L3WorkerExecutionError
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
        if not self.responses:
            raise AssertionError("Hermes should not be called")
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
async def test_runtime_stops_before_l2_when_repair_budget_is_exhausted() -> None:
    run = ProcessRun(
        playbook_key="build-in-public",
        goal="Share progress",
        status=RunStatus.RUNNING,
        input={"require_human_approval": False},
    )
    store = FakeStore(run)
    store.events.append(
        {
            "event_type": "incident_brief",
            "task_id": "task-1",
            "payload": {
                "worker_profile": "signal-collector",
                "failure_type": "input_validation",
                "error": "signals are missing",
                "retry_count_remaining": 0,
            },
        }
    )

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), FakeHermes([])).run_until_blocked_or_done(run.id)

    assert output["status"] == "failed"
    assert any(event["event_type"] == "repair_budget_exhausted" for event in store.events)
    assert "signal-collector/input_validation" in store.run.output["reason"]
    assert any(artifact.artifact_type.value == "run_diagnosis" for artifact in store.artifacts)
    assert store.improvement_proposals


@pytest.mark.asyncio
async def test_runtime_fails_invalid_trend_provider_before_l2() -> None:
    run = ProcessRun(
        playbook_key="build-in-public-trend-radar",
        goal="Run trend radar",
        status=RunStatus.CREATED,
        input={
            "require_human_approval": True,
            "inputs": {
                "query": "agent runtime observability",
                "providers": ["github", "notarealprovider"],
                "channels": ["x"],
            },
        },
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), FakeHermes([])).run_until_blocked_or_done(run.id)

    assert output["status"] == "failed"
    assert "unsupported providers" in store.run.output["reason"]
    assert any(event["event_type"] == "run_input_validation_failed" for event in store.events)
    assert any(artifact.artifact_type.value == "run_diagnosis" for artifact in store.artifacts)
    assert store.improvement_proposals[0].proposal_type == "improve_policy"


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


@pytest.mark.asyncio
async def test_p1_workflow_reuses_existing_real_artifact_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    run = ProcessRun(
        playbook_key="p1-operator-outreach",
        goal="Resume P1 proof without repeating completed source collection",
        status=RunStatus.RUNNING,
        input={
            "playbook_key": "p1-operator-outreach",
            "l2_mode": "execution",
            "goal": "Resume P1 proof without repeating completed source collection",
            "inputs": {"mode": "full_pipeline", "sources": ["apify_linkedin"], "require_human_approval": False},
            "require_human_approval": False,
        },
    )
    store = FakeStore(run)
    stale_failed_task = WorkOrder(
        run_id=run.id,
        task_type="collect_sources",
        worker_profile="p1-source-collector",
        goal="old failed source collection task",
        status=TaskStatus.FAILED,
    )
    store.tasks.append(stale_failed_task)
    await store.add_artifact(
        Artifact(
            run_id=run.id,
            task_id=stale_failed_task.id,
            artifact_type=ArtifactType.P1_SOURCE_BATCH,
            payload={"source": "apify_linkedin", "lead_candidates": [{"lead_id": "lead-1", "name": "Ava Operator"}], "source_attempts": [{"source": "apify_linkedin", "result_count": 1}]},
        )
    )
    runtime = ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), FakeHermes([]))
    executed_workers: list[str] = []

    async def fake_execute_task(run_id: UUID, task: dict[str, Any], profile: dict[str, Any]) -> None:
        executed_workers.append(task["worker_profile"])
        artifact_type = ArtifactType(task["artifact_type"])
        payloads = {
            ArtifactType.P1_SOURCE_BATCH: {"source": "apify_linkedin", "lead_candidates": [{"lead_id": "lead-1", "name": "Ava Operator"}], "source_attempts": [{"source": "apify_linkedin", "result_count": 1}]},
            ArtifactType.P1_LEAD_CANDIDATES: {"lead_candidates": [{"lead_id": "lead-1", "name": "Ava Operator"}]},
            ArtifactType.P1_NORMALIZED_LEADS: {"normalized_leads": [{"lead_id": "lead-1", "name": "Ava Operator"}]},
            ArtifactType.P1_TRIAGE_SCORES: {"triage_scores": [{"lead_id": "lead-1", "score": 91, "qualified": True}]},
            ArtifactType.P1_DOSSIERS: {"p1_dossiers": [{"lead_id": "lead-1", "name": "Ava Operator"}]},
            ArtifactType.P1_LIVE_INTELLIGENCE: {"p1_dossiers": [{"lead_id": "lead-1", "name": "Ava Operator", "live_context": []}]},
            ArtifactType.P1_GATEWAY_EVALUATIONS: {"gateway_evaluations": [{"lead_id": "lead-1", "decision": "approved"}]},
            ArtifactType.P1_FORGE_QUEUE: {"forge_queue": [{"lead_id": "lead-1", "operator_name": "Ava Operator"}]},
            ArtifactType.P1_OUTREACH_DRAFTS: {"outreach_drafts": [{"lead_id": "lead-1", "body": "ABRT hello"}]},
            ArtifactType.P1_OUTREACH_APPROVAL_PACKAGE: {"outreach_drafts": [{"lead_id": "lead-1", "body": "ABRT hello"}]},
            ArtifactType.P1_METRICS_REPORT: {"metrics": {"raw_leads": 1, "drafted": 1}},
        }
        await store.add_artifact(Artifact(run_id=run_id, artifact_type=artifact_type, payload=payloads[artifact_type]))

    monkeypatch.setattr(runtime, "_execute_task", fake_execute_task)

    output = await runtime.run_until_blocked_or_done(run.id)

    assert output["status"] == "completed"
    assert "p1-source-collector" not in executed_workers
    assert any(event["event_type"] == "p1_source_batch_reused" for event in store.events)
    checkpoint_event = next(event for event in store.events if event["event_type"] == "p1_source_batch_reused")
    assert checkpoint_event["payload"]["artifact_type"] == ArtifactType.P1_SOURCE_BATCH.value


@pytest.mark.asyncio
async def test_p1_force_rerun_ignores_existing_checkpoint(monkeypatch: pytest.MonkeyPatch) -> None:
    run = ProcessRun(
        playbook_key="p1-operator-outreach",
        goal="Force a P1 source rerun",
        status=RunStatus.RUNNING,
        input={
            "playbook_key": "p1-operator-outreach",
            "l2_mode": "execution",
            "goal": "Force a P1 source rerun",
            "inputs": {
                "mode": "source_only",
                "sources": ["apify_linkedin"],
                "force_rerun": True,
                "require_human_approval": False,
                "use_triage_cache": True,
                "triage_cache_dir": "/tmp/p1-triage-cache-test",
            },
            "require_human_approval": False,
        },
    )
    store = FakeStore(run)
    await store.add_artifact(
        Artifact(
            run_id=run.id,
            artifact_type=ArtifactType.P1_LEAD_CANDIDATES,
            payload={"lead_candidates": [{"lead_id": "old-lead", "name": "Old Lead"}]},
        )
    )
    runtime = ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), FakeHermes([]))
    executed_workers: list[str] = []
    task_inputs_by_worker: dict[str, dict[str, Any]] = {}

    async def fake_execute_task(run_id: UUID, task: dict[str, Any], profile: dict[str, Any]) -> None:
        executed_workers.append(task["worker_profile"])
        task_inputs_by_worker[task["worker_profile"]] = task["inputs"]
        artifact_type = ArtifactType(task["artifact_type"])
        payloads = {
            ArtifactType.P1_SOURCE_BATCH: {"source": "apify_linkedin", "lead_candidates": [{"lead_id": "new-lead", "name": "New Lead"}], "source_attempts": [{"source": "apify_linkedin", "result_count": 1}]},
            ArtifactType.P1_LEAD_CANDIDATES: {"lead_candidates": [{"lead_id": "new-lead", "name": "New Lead"}]},
            ArtifactType.P1_NORMALIZED_LEADS: {"normalized_leads": [{"lead_id": "new-lead", "name": "New Lead"}]},
            ArtifactType.P1_TRIAGE_SCORES: {"triage_scores": [{"lead_id": "new-lead", "score": 88, "qualified": True}]},
            ArtifactType.P1_DOSSIERS: {"p1_dossiers": [{"lead_id": "new-lead", "name": "New Lead"}]},
            ArtifactType.P1_METRICS_REPORT: {"metrics": {"raw_leads": 1, "dossiers": 1}},
        }
        await store.add_artifact(Artifact(run_id=run_id, artifact_type=artifact_type, payload=payloads[artifact_type]))

    monkeypatch.setattr(runtime, "_execute_task", fake_execute_task)

    output = await runtime.run_until_blocked_or_done(run.id)

    assert output["status"] == "completed"
    assert executed_workers[0] == "p1-source-collector"
    assert task_inputs_by_worker["p1-triage-scorer"]["use_triage_cache"] is True
    assert task_inputs_by_worker["p1-triage-scorer"]["triage_cache_dir"] == "/tmp/p1-triage-cache-test"
    assert not any(event["event_type"] == "p1_checkpoint_reused" for event in store.events)


def _p2_payload_for_artifact(artifact_type: ArtifactType) -> dict[str, Any]:
    startup = {
        "Company Name": "Acme AI",
        "Website URL": "https://acme.ai",
        "Website Final URL": "https://acme.ai",
        "Founder LinkedIn URL(s)": "https://linkedin.com/in/acme-founder",
        "Founder LinkedIn Count": 1,
        "Country of Incorporation": "US",
        "Startup Stage": "Seed",
        "Additional Decision-Useful Info": "B2B AI workflow automation with early ARR.",
        "Direction": "AI / Generative Tech",
        "Ohio Fit Score": "84",
        "Evidence Quality Score": 70,
        "Website Verification Status": "Verified",
        "Website Verification Note": "Official website verified.",
        "Judge Tag": "Approve",
        "Judge Reason": "Strong ICP fit.",
        "Source Tab": "From Database",
        "ICP Version": "p2-ohio-v1",
    }
    return {
        ArtifactType.P2_RAW_STARTUP_ROWS: {"raw_startup_rows": [startup], "sheet_metadata": [], "drift_report": []},
        ArtifactType.P2_NORMALIZED_STARTUPS: {"normalized_startups": [startup], "rejected_startups": []},
        ArtifactType.P2_FOUNDER_LINKS_RESOLVED: {"founder_links_resolved": [startup]},
        ArtifactType.P2_WEBSITE_VERIFICATION: {"website_verification": [startup], "verification_summary": {"corrected_urls": 0, "tbc_urls": 0}},
        ArtifactType.P2_SECTOR_CLASSIFICATION: {"sector_classification": [startup], "direction_counts": {"AI / Generative Tech": 1}},
        ArtifactType.P2_ICP_SCORES: {"icp_scores": [startup], "score_summary": {"high_fit_count": 1}},
        ArtifactType.P2_SYNTHETIC_BENCHMARKS: {"synthetic_benchmarks": [{**startup, "Data Type": "synthetic benchmark data"}], "synthetic_summary": {"synthetic_fields_filled": 12}},
        ArtifactType.P2_JUDGE_RESULTS: {"judge_results": [startup], "judge_summary": {"input_count": 1, "Approve": 1, "Reject": 0, "Needs manual verification": 0}},
        ArtifactType.P2_SUITABLE_STARTUPS: {"suitable_startups": [startup], "headers": list(startup.keys()), "excluded_duplicates": [], "rejected_startups": [], "duplicates_removed": 0},
        ArtifactType.P2_APPROVAL_PACKAGE: {
            "passed": True,
            "score": 1.0,
            "checks": {"all_approved": True, "no_duplicates": True},
            "reasons": [],
            "approval_package": {"approval_required": True, "output_tab": "Suitable Startups", "headers": list(startup.keys()), "suitable_startups": [startup], "row_count": 1, "reasons": []},
            "suitable_startups": [startup],
        },
        ArtifactType.P2_GOOGLE_SHEETS_SYNC_RESULT: {"sync_result": {"output_tab": "Suitable Startups", "row_count": 1, "mode": "replace"}, "external_actions": [{"type": "google_sheets_write", "status": "completed"}]},
        ArtifactType.P2_METRICS_REPORT: {"metrics": {"input_rows": 1, "normalized_rows": 1, "approved_startups": 1, "suitable_rows": 1, "duplicates_removed": 0}, "summary": "ok"},
    }[artifact_type]


@pytest.mark.asyncio
async def test_p2_sheet_pipeline_completes_without_google_write(monkeypatch: pytest.MonkeyPatch) -> None:
    run = ProcessRun(
        playbook_key="p2-startup-sourcing",
        goal="Build suitable startups",
        status=RunStatus.CREATED,
        input={
            "playbook_key": "p2-startup-sourcing",
            "l2_mode": "execution",
            "goal": "Build suitable startups",
            "inputs": {"mode": "sheet_pipeline", "spreadsheet_id": "sheet-1", "allow_google_sheet_write": False},
            "require_human_approval": True,
        },
    )
    store = FakeStore(run)
    runtime = ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), FakeHermes([]))
    executed: list[str] = []

    async def fake_execute_task(run_id: UUID, task: dict[str, Any], profile: dict[str, Any]) -> None:
        executed.append(task["worker_profile"])
        artifact_type = ArtifactType(task["artifact_type"])
        await store.add_artifact(Artifact(run_id=run_id, artifact_type=artifact_type, payload=_p2_payload_for_artifact(artifact_type)))

    monkeypatch.setattr(runtime, "_execute_task", fake_execute_task)

    output = await runtime.run_until_blocked_or_done(run.id)

    assert output["status"] == "completed"
    assert output["output"]["external_sync_requested"] is False
    assert "p2-google-sheets-syncer" not in executed
    assert executed[:3] == ["p2-sheet-reader", "p2-startup-normalizer", "p2-founder-link-resolver"]
    assert any(artifact.artifact_type == ArtifactType.P2_EXTERNAL_ACTION_PREVIEW for artifact in store.artifacts)


@pytest.mark.asyncio
async def test_p2_google_sheet_write_waits_for_approval_then_syncs(monkeypatch: pytest.MonkeyPatch) -> None:
    run = ProcessRun(
        playbook_key="p2-startup-sourcing",
        goal="Build and sync suitable startups",
        status=RunStatus.CREATED,
        input={
            "playbook_key": "p2-startup-sourcing",
            "l2_mode": "execution",
            "goal": "Build and sync suitable startups",
            "inputs": {"mode": "sheet_pipeline", "spreadsheet_id": "sheet-1", "allow_google_sheet_write": True},
            "require_human_approval": True,
        },
    )
    store = FakeStore(run)
    runtime = ProcessRuntime(store, ProceduralRegistry(Path("registries")), FakeMemory(), FakeHermes([]))
    executed: list[str] = []

    async def fake_execute_task(run_id: UUID, task: dict[str, Any], profile: dict[str, Any]) -> None:
        executed.append(task["worker_profile"])
        artifact_type = ArtifactType(task["artifact_type"])
        await store.add_artifact(Artifact(run_id=run_id, artifact_type=artifact_type, payload=_p2_payload_for_artifact(artifact_type)))

    monkeypatch.setattr(runtime, "_execute_task", fake_execute_task)

    waiting = await runtime.run_until_blocked_or_done(run.id)
    assert waiting["status"] == "waiting_approval"
    assert waiting["output"]["external_sync_requested"] is True
    assert "p2-google-sheets-syncer" not in executed

    final = await runtime.apply_control(run.id, "approve", {})

    assert final["status"] == "completed"
    assert final["output"]["external_sync_performed"] is True
    assert final["output"]["external_sync_result"]["row_count"] == 1
    assert "p2-google-sheets-syncer" in executed


def test_worker_error_classification_preserves_real_provider_failures() -> None:
    error = L3WorkerExecutionError(
        '{"error_type":"WorkerInputError","message":"trend providers failed","provider_failures":{"arxiv":"Rate exceeded"}}'
    )

    assert ProcessRuntime._classify_worker_error(error) == "provider_request_failed"


def test_worker_error_classification_does_not_treat_empty_provider_metadata_as_provider_failure() -> None:
    error = L3WorkerExecutionError(
        '{"error_type":"WorkerInputError","message":"missing required non-empty string: draft.text","provider_failures":{}}'
    )

    assert ProcessRuntime._classify_worker_error(error) == "output_schema"


def test_worker_error_classification_detects_real_provider_no_results() -> None:
    error = L3WorkerExecutionError(
        '{"error_type":"P1WorkerInputError","message":"real P1 sourcing returned no lead candidates for sources=[\'apify_funding\']"}'
    )

    assert ProcessRuntime._classify_worker_error(error) == "provider_no_results"


def test_worker_error_classification_detects_missing_provider_credential() -> None:
    error = L3WorkerExecutionError(
        '{"error_type":"P1WorkerInputError","message":"missing environment variable: EXA_API_KEY"}'
    )

    assert ProcessRuntime._classify_worker_error(error) == "missing_provider_credential"


def test_worker_error_classification_detects_no_eligible_candidates() -> None:
    error = L3WorkerExecutionError(
        '{"error_type":"P1WorkerInputError","message":"no gateway-approved operators for outreach; bypassed=1"}'
    )

    assert ProcessRuntime._classify_worker_error(error) == "no_eligible_candidates"


def test_worker_error_classification_detects_provider_permission_required() -> None:
    error = L3WorkerExecutionError(
        '{"error_type":"P1WorkerInputError","message":"full-permission-actor-not-approved: approve its permissions"}'
    )

    assert ProcessRuntime._classify_worker_error(error) == "provider_permission_required"
