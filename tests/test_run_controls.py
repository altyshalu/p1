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
async def test_approve_control_runs_requested_p1_external_sync(monkeypatch) -> None:
    store = FakeStore()
    store.run.playbook_key = "p1-operator-outreach"
    store.run.output = {
        "approval_package": {"approval_package": {"outreach_drafts": [{"name": "A", "text": "B"}]}},
        "external_sync_requested": True,
        "external_sync_performed": False,
    }
    run_id = uuid4()
    runtime = ProcessRuntime(store, None, None, None)

    async def fake_load_playbook(playbook_key):
        return {"allowed_workers": ["p1-google-sheets-syncer"]}

    async def fake_allowed_worker_profiles(playbook):
        return {
            "p1-google-sheets-syncer": {
                "description": "Approval-gated real Google Sheets sync for P1.",
                "allowed_tools": ["google-sheets-write-tool"],
            }
        }

    async def fake_execute_task(run_id, task, profile):
        store.artifacts.append(
            {
                "id": str(uuid4()),
                "task_id": None,
                "artifact_type": ArtifactType.P1_EXTERNAL_SYNC_RESULT.value,
                "payload": {"sync_result": {"row_count": 1}},
            }
        )

    monkeypatch.setattr(runtime, "_load_playbook", fake_load_playbook)
    monkeypatch.setattr(runtime, "_allowed_worker_profiles", fake_allowed_worker_profiles)
    monkeypatch.setattr(runtime, "_execute_task", fake_execute_task)
    monkeypatch.setattr(runtime, "_record_run_diagnosis", lambda run_id: _completed_async())

    result = await runtime.apply_control(run_id, "approve", {"spreadsheet_id": "real-sheet-id"})

    assert result["status"] == "completed"
    assert result["output"]["external_sync_performed"] is True
    assert result["output"]["external_sync_result"]["row_count"] == 1
    assert [event["event_type"] for event in store.events] == [
        "run_control",
        "p1_external_sync_approved",
        "p1_external_sync_completed",
        "run_finished",
    ]


async def _completed_async() -> None:
    return None
