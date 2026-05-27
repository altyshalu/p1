from uuid import uuid4

from l2l3_protocol.core.schemas import ArtifactType, ImprovementProposalStatus
from l2l3_protocol.runtime.diagnostics import analyze_run


def test_failed_run_diagnosis_uses_incident_brief_evidence_and_proposes_improvement() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [{"id": task_id, "worker_profile": "trend-source-collector", "status": "failed"}],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "trend-source-collector",
                    "failure_type": "provider_no_results",
                    "error": "huggingface search failed after 2 real attempts",
                    "retry_count_remaining": 0,
                    "repair_guidance": {"l2_can": ["retry the same provider with provider_repairs using alternative real queries"]},
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.artifact_type == ArtifactType.RUN_DIAGNOSIS
    assert diagnosis.payload["outcome"] == "failed"
    assert diagnosis.payload["root_cause"] == "tool_or_provider_failure"
    assert diagnosis.payload["evidence"][0]["event_type"] == "incident_brief"
    assert "huggingface search failed" in diagnosis.payload["summary"]
    assert proposals
    assert proposals[0].status == ImprovementProposalStatus.PROPOSED
    assert proposals[0].proposal_type == "improve_tool"
    assert proposals[0].source_run_id == run["id"]
    assert proposals[0].evidence[0]["task_id"] == task_id


def test_successful_run_with_no_incidents_records_no_improvement_needed() -> None:
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [{"worker_profile": "trend-draft-quality-judge", "status": "completed"}],
        "artifacts": [{"artifact_type": "channel_drafts", "payload": {"drafts": [{"text": "real draft"}]}}],
        "evals": [{"eval_key": "trend-draft-quality", "passed": True, "score": 1.0}],
        "events": [{"event_type": "run_finished", "payload": {"status": "waiting_approval"}}],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["outcome"] == "waiting_approval"
    assert diagnosis.payload["root_cause"] == "none"
    assert diagnosis.payload["improvement_needed"] is False
    assert diagnosis.payload["proposal_reason"] == "No improvement proposal needed for this run."
    assert proposals == []


def test_max_turn_failure_after_repeated_eval_repairs_is_repeated_repair() -> None:
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [],
        "artifacts": [],
        "evals": [
            {
                "eval_key": "trend-claim-grounding",
                "passed": False,
                "score": 0.3333333333333333,
                "threshold": 1.0,
                "reasons": ["Draft has no claims."],
            }
        ],
        "events": [
            {"event_type": "incident_brief", "payload": {"failure_type": "eval_failed", "worker_profile": "claim-grounding-judge"}},
            {"event_type": "incident_brief", "payload": {"failure_type": "eval_failed", "worker_profile": "claim-grounding-judge"}},
            {"event_type": "run_failed", "payload": {"reason": "max_supervisor_turns exceeded"}},
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["outcome"] == "failed"
    assert diagnosis.payload["root_cause"] == "repeated_repair"
    assert diagnosis.payload["repeated_repair"] is True
    assert "max_supervisor_turns exceeded" in diagnosis.payload["summary"]
    assert proposals[0].proposal_type == "improve_playbook"
