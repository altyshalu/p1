from uuid import uuid4

import pytest

from l2l3_protocol.core.schemas import ProcessRun, RunStatus
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

    async def set_run_status(self, run_id, status, output=None) -> None:
        self.run.status = status
        if output is not None:
            self.run.output = output

    async def add_event(self, run_id, event_type, payload, task_id=None) -> None:
        self.events.append({"event_type": event_type, "payload": payload})

    async def get_run(self, run_id):
        return {
            "id": str(run_id),
            "playbook_key": self.run.playbook_key,
            "l2_mode": self.run.l2_mode.value,
            "goal": self.run.goal,
            "status": self.run.status.value,
            "input": self.run.input,
            "output": self.run.output,
            "tasks": [],
            "artifacts": [],
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
