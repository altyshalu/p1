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
    assert proposals[0].target_component == "trend-source-collector/provider:huggingface"
    assert proposals[0].failure_signature == "provider_no_results:trend-source-collector"
    assert "Hugging Face provider repair" in proposals[0].proposed_change
    assert proposals[0].source_run_id == run["id"]
    assert proposals[0].evidence[0]["task_id"] == task_id
    assert proposals[0].behavior_change_requires_approval is True
    assert proposals[0].proof_spec["real_run_required"] is True
    assert proposals[0].proof_spec["baseline_run_id"] == run["id"]
    assert proposals[0].proof_spec["expected_absent_signature"] == "provider_no_results:trend-source-collector"


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
    assert proposals[0].target_component == "playbook:repair-stop-rules"


def test_diagnosis_prefers_typed_incident_over_untyped_task_wrapper() -> None:
    task_id = str(uuid4())
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [],
        "artifacts": [],
        "evals": [{"eval_key": "trend-draft-quality", "passed": True, "score": 1.0}],
        "events": [
            {
                "event_type": "task_failed",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "trend-source-collector",
                    "error": "trend providers failed",
                },
            },
            {
                "event_type": "incident_brief",
                "task_id": task_id,
                "payload": {
                    "worker_profile": "trend-source-collector",
                    "failure_type": "provider_no_results",
                    "error": "huggingface search returned no results",
                },
            },
            {"event_type": "run_finished", "payload": {"status": "waiting_approval"}},
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "tool_or_provider_failure"
    assert "huggingface search returned no results" in diagnosis.payload["summary"]
    assert proposals[0].proposal_type == "improve_tool"


def test_claim_grounding_failure_proposal_targets_eval_contract() -> None:
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [],
        "artifacts": [],
        "evals": [
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-claim-grounding",
                "passed": False,
                "score": 0.3333333333333333,
                "threshold": 1.0,
                "reasons": ["Draft has no claims."],
            }
        ],
        "events": [
            {
                "event_type": "incident_brief",
                "payload": {
                    "worker_profile": "claim-grounding-judge",
                    "failure_type": "eval_failed",
                    "error": "eval did not meet threshold",
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "quality_gate_failed"
    assert proposals[0].proposal_type == "improve_eval"
    assert proposals[0].target_component == "claim-grounding-judge/trend-claim-grounding"
    assert proposals[0].failure_signature == "eval_failed:claim-grounding-judge"
    assert "claim-grounding contract" in proposals[0].proposed_change


def test_repaired_eval_failure_does_not_create_terminal_quality_proposal() -> None:
    run = {
        "id": str(uuid4()),
        "status": "waiting_approval",
        "tasks": [],
        "artifacts": [],
        "evals": [
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-claim-grounding",
                "passed": False,
                "score": 0.6666666666666666,
                "threshold": 1.0,
                "reasons": ["Draft has no claims."],
            },
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-claim-grounding",
                "passed": True,
                "score": 1.0,
                "threshold": 1.0,
                "reasons": [],
            },
            {
                "task_id": str(uuid4()),
                "eval_key": "trend-draft-quality",
                "passed": True,
                "score": 1.0,
                "threshold": 0.8,
                "reasons": [],
            },
        ],
        "events": [
            {
                "event_type": "incident_brief",
                "payload": {
                    "worker_profile": "claim-grounding-judge",
                    "failure_type": "eval_failed",
                    "error": "eval did not meet threshold",
                    "eval_result": {
                        "eval_key": "trend-claim-grounding",
                        "passed": False,
                    },
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "none"
    assert diagnosis.payload["improvement_needed"] is False
    assert diagnosis.payload["evidence"] == []
    assert proposals == []


def test_invalid_provider_proposal_targets_trend_radar_inputs() -> None:
    run = {
        "id": str(uuid4()),
        "status": "failed",
        "tasks": [],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "run_input_validation_failed",
                "payload": {
                    "failure_type": "input_validation",
                    "error": "unsupported providers requested: ['notarealprovider']; supported providers: ['arxiv', 'github', 'huggingface']",
                },
            }
        ],
    }

    diagnosis, proposals = analyze_run(run)

    assert diagnosis.payload["root_cause"] == "bad_or_missing_input"
    assert proposals[0].proposal_type == "improve_policy"
    assert proposals[0].target_component == "trend-radar/input.providers"
    assert proposals[0].failure_signature == "input_validation:trend-radar/input.providers"
