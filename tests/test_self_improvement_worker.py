from uuid import uuid4

from l2l3_protocol.core.schemas import FailureLearning
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
