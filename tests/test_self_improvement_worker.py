from uuid import uuid4

import pytest

from l2l3_protocol.core.schemas import FailureLearning, WorkOrder
from l2l3_protocol.runtime.l3_executor import L3SandboxExecutor
from l2l3_protocol.workers.self_improvement_worker import review_recent_runs


def test_self_improvement_reviewer_worker_returns_system_review_backlog() -> None:
    run_id = str(uuid4())
    learning = FailureLearning(
        failure_signature="provider_no_results:trend-source-collector",
        target_component="trend-source-collector/provider:huggingface",
        root_cause="tool_or_provider_failure",
        playbook_key="build-in-public-trend-radar",
        proposal_type="improve_tool",
        learning_summary="Hugging Face returned no results on a real run.",
        proposed_next_step="Try approved dataset and space resource types before exhausting Hugging Face.",
        risk="Behavior-changing improvements require explicit approval before implementation.",
        success_check="Repeat a comparable real run.",
        occurrence_count=2,
        first_seen_run_id=run_id,
        last_seen_run_id=run_id,
        evidence_refs=[{"run_id": run_id, "event_type": "incident_brief"}],
        run_ids=[run_id],
    )

    output = review_recent_runs(
        {
            "inputs": {
                "recent_runs": [{"id": run_id, "playbook_key": "build-in-public-trend-radar", "status": "failed"}],
                "failure_learnings": [learning.model_dump(mode="json")],
                "limit": 10,
                "playbook_key": "build-in-public-trend-radar",
            },
            "worker_profile": "self-improvement-reviewer",
            "task_type": "review_recent_runs",
        },
        {},
    )

    review = output["system_review"]
    assert review["run_count"] == 1
    assert review["learning_count"] == 1
    assert review["findings"][0]["failure_signature"] == "provider_no_results:trend-source-collector"
    assert review["recommendations"][0]["approval_required"] is True


@pytest.mark.asyncio
async def test_self_improvement_reviewer_runs_as_real_subprocess_worker() -> None:
    run_id = str(uuid4())
    learning = FailureLearning(
        failure_signature="output_schema:stop-slop-editor",
        target_component="stop-slop-editor",
        root_cause="worker_output_contract_failed",
        playbook_key="build-in-public-trend-radar",
        proposal_type="improve_eval",
        learning_summary="Stop-slop editor received a draft without text.",
        proposed_next_step="Normalize body into text before editing.",
        risk="Behavior-changing improvements require explicit approval before implementation.",
        success_check="Repeat a comparable real run.",
        first_seen_run_id=run_id,
        last_seen_run_id=run_id,
        evidence_refs=[{"run_id": run_id, "event_type": "incident_brief"}],
        run_ids=[run_id],
    )
    work_order = WorkOrder(
        run_id=uuid4(),
        task_type="review_recent_runs",
        goal="Review recent runs.",
        worker_profile="self-improvement-reviewer",
        worker_type="sandboxed_subprocess",
        inputs={
            "recent_runs": [{"id": run_id, "playbook_key": "build-in-public-trend-radar"}],
            "failure_learnings": [learning.model_dump(mode="json")],
            "limit": 10,
            "playbook_key": "build-in-public-trend-radar",
        },
        output_schema={"type": "object", "required": ["system_review"]},
        budget={"max_seconds": 30},
    )

    output = await L3SandboxExecutor().run(
        work_order,
        {"source": "test"},
        {"entrypoint": "l2l3_protocol.workers.self_improvement_worker", "worker_type": "sandboxed_subprocess"},
    )

    assert output["_worker_execution"]["worker_profile"] == "self-improvement-reviewer"
    assert output["system_review"]["findings"][0]["failure_signature"] == "output_schema:stop-slop-editor"
