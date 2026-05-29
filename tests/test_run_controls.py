from uuid import uuid4

import pytest

from l2l3_protocol.core.schemas import Artifact, ArtifactType, ProcessRun, RunStatus
from l2l3_protocol.runtime.process_runtime import ProcessRuntime


class FakeStore:
    def __init__(self) -> None:
        self.run = ProcessRun(
            playbook_key="build-in-public-trend-radar",
            goal="real trend radar run",
            status=RunStatus.WAITING_APPROVAL,
            input={"require_human_approval": True},
        )
        self.events: list[dict] = []
        self.artifacts: list[dict] = []
        self.tasks: list[dict] = []

    async def set_run_status(self, run_id, status, output=None) -> None:
        self.run.status = status
        if output is not None:
            self.run.output = output

    async def add_event(self, run_id, event_type, payload, task_id=None) -> None:
        self.events.append({"event_type": event_type, "payload": payload})

    async def add_artifact(self, artifact: Artifact) -> None:
        self.artifacts.append(
            {
                "id": str(artifact.id),
                "task_id": str(artifact.task_id) if artifact.task_id else None,
                "artifact_type": artifact.artifact_type.value,
                "payload": artifact.payload,
            }
        )

    async def get_run(self, run_id):
        return {
            "id": str(run_id),
            "playbook_key": self.run.playbook_key,
            "l2_mode": self.run.l2_mode.value,
            "goal": self.run.goal,
            "status": self.run.status.value,
            "input": self.run.input,
            "output": self.run.output,
            "tasks": self.tasks,
            "artifacts": self.artifacts,
            "evals": [],
            "events": self.events,
        }


@pytest.mark.asyncio
async def test_reject_control_marks_run_failed_with_reason() -> None:
    store = FakeStore()
    run_id = uuid4()

    result = await ProcessRuntime(store, None, None, None).apply_control(run_id, "reject", {"reason": "Needs stronger source."})

    assert result["status"] == "failed"
    assert result["output"]["reason"] == "Needs stronger source."
    assert store.events[-1]["event_type"] == "run_control"


@pytest.mark.asyncio
async def test_request_edit_control_moves_run_to_waiting_user() -> None:
    store = FakeStore()
    store.run.output = {"final": {"drafts": [{"text": "latest draft"}]}}
    run_id = uuid4()

    result = await ProcessRuntime(store, None, None, None).apply_control(run_id, "request_edit", {"message": "Make it more direct."})

    assert result["status"] == "waiting_user"
    assert result["output"]["requested_edit"] == "Make it more direct."
    assert result["output"]["final"]["drafts"][0]["text"] == "latest draft"
    assert store.events[-1]["payload"]["action"] == "request_edit"


@pytest.mark.asyncio
async def test_approve_control_marks_non_p1_run_completed() -> None:
    store = FakeStore()
    run_id = uuid4()

    result = await ProcessRuntime(store, None, None, None).apply_control(run_id, "approve", {})

    assert result["status"] == "completed"
    assert store.events[-1]["payload"]["action"] == "approve"


@pytest.mark.asyncio
async def test_approve_control_runs_requested_p1_external_syncs(monkeypatch) -> None:
    store = FakeStore()
    store.run.playbook_key = "p1-operator-outreach"
    store.run.output = {
        "approval_package": {"approval_package": {"outreach_drafts": [{"name": "A", "text": "B"}]}},
        "external_sync_requested": True,
        "outreach_master_sync_requested": True,
        "external_sync_performed": False,
        "outreach_master_sync_performed": False,
    }
    run_id = uuid4()
    runtime = ProcessRuntime(store, None, None, None)

    async def fake_load_playbook(playbook_key):
        return {"allowed_workers": ["p1-google-sheets-syncer", "p1-outreach-master-syncer", "p1-metrics-reporter"]}

    async def fake_allowed_worker_profiles(playbook):
        return {
            "p1-google-sheets-syncer": {
                "description": "Approval-gated real Google Sheets sync for P1.",
                "allowed_tools": ["google-sheets-write-tool"],
            },
            "p1-outreach-master-syncer": {
                "description": "Approval-gated real Outreach Drafts Master sync for P1.",
                "allowed_tools": ["p1-dossier-store-tool"],
            },
            "p1-metrics-reporter": {
                "description": "Build P1 funnel metrics.",
                "allowed_tools": [],
            }
        }

    async def fake_execute_task(run_id, task, profile):
        if task["worker_profile"] == "p1-google-sheets-syncer":
            artifact_type = ArtifactType.P1_EXTERNAL_SYNC_RESULT.value
            payload = {"sync_result": {"row_count": 1}}
        elif task["worker_profile"] == "p1-outreach-master-syncer":
            artifact_type = ArtifactType.P1_OUTREACH_MASTER_SYNC_RESULT.value
            payload = {"sync_result": {"written_count": 1}}
        else:
            artifact_type = ArtifactType.P1_METRICS_REPORT.value
            payload = {"metrics": {"sheet_written": 1, "outreach_master_written": 1}}
        store.artifacts.append({"id": str(uuid4()), "task_id": None, "artifact_type": artifact_type, "payload": payload})

    monkeypatch.setattr(runtime, "_load_playbook", fake_load_playbook)
    monkeypatch.setattr(runtime, "_allowed_worker_profiles", fake_allowed_worker_profiles)
    monkeypatch.setattr(runtime, "_execute_task", fake_execute_task)
    monkeypatch.setattr(runtime, "_record_run_diagnosis", lambda run_id: _completed_async())

    result = await runtime.apply_control(run_id, "approve", {"spreadsheet_id": "real-sheet-id"})

    assert result["status"] == "completed"
    assert result["output"]["external_sync_performed"] is True
    assert result["output"]["outreach_master_sync_performed"] is True
    assert result["output"]["external_sync_result"]["row_count"] == 1
    assert result["output"]["outreach_master_sync_result"]["written_count"] == 1
    assert result["output"]["metrics"]["outreach_master_written"] == 1
    assert [event["event_type"] for event in store.events] == [
        "run_control",
        "p1_external_sync_approved",
        "p1_external_sync_completed",
        "p1_outreach_master_sync_approved",
        "p1_outreach_master_sync_completed",
        "p1_metrics_report_created",
        "run_finished",
    ]


async def _completed_async() -> None:
    return None


@pytest.mark.asyncio
async def test_build_p1_approval_preview_contains_exact_targets_and_ids() -> None:
    runtime = ProcessRuntime(FakeStore(), None, None, None)
    run_id = uuid4()

    preview = runtime._build_p1_approval_preview(
        run_id=run_id,
        inputs={
            "spreadsheet_id": "sheet-123",
            "google_sheet_tab": "P1_L2L3_NEW_LEADS",
            "outreach_master_path": "/tmp/outreach.json",
            "data_lake_dossier_path": "/tmp/dossiers",
        },
        approval_package={
            "outreach_drafts": [
                {
                    "lead_id": "lead-1",
                    "name": "Arianna Simpson",
                    "linkedin_url": "https://www.linkedin.com/in/ariannasimpson",
                    "runtime_source": "p1-operator-outreach",
                    "idempotency_key": f"{run_id}:lead-1",
                }
            ],
            "reasons": ["low risk"],
        },
        dossiers=[{"identity": {"lead_id": "lead-1", "name": "Arianna Simpson"}}],
        allow_sheet_write=True,
        allow_outreach_master_write=True,
        allow_data_lake_write=True,
    )

    assert preview["google_sheets"]["spreadsheet_id"] == "sheet-123"
    assert preview["google_sheets"]["tab_name"] == "P1_L2L3_NEW_LEADS"
    assert preview["google_sheets"]["rows"][0]["lead_id"] == "lead-1"
    assert preview["google_sheets"]["rows"][0]["idempotency_key"] == f"{run_id}:lead-1"
    assert preview["outreach_master"]["path"] == "/tmp/outreach.json"
    assert preview["data_lake"]["path"] == "/tmp/dossiers"
    assert preview["data_lake"]["files"][0]["lead_id"] == "lead-1"
    assert preview["risk_summary"] == ["low risk"]
