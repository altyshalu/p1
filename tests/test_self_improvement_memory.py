from uuid import uuid4

from l2l3_protocol.core.schemas import ImprovementProposal
from l2l3_protocol.runtime.self_improvement import (
    build_failure_learnings,
    build_recent_system_review,
    proposal_from_failure_learning,
)


def _proposal(run_id: str, signature: str = "eval_failed:claim-grounding-judge") -> ImprovementProposal:
    return ImprovementProposal(
        run_id=uuid4(),
        source_run_id=run_id,
        proposal_type="improve_eval",
        target_component="claim-grounding-judge/trend-claim-grounding",
        failure_signature=signature,
        problem="Draft has no claims.",
        proposed_change="Fix the claim-grounding contract.",
        risk="Behavior-changing improvements require explicit approval before implementation.",
        success_check="Repeat a comparable real run.",
        evidence=[{"event_type": "eval_result_failed", "failure_type": "eval_failed", "error": "Draft has no claims."}],
    )


def test_failure_learning_is_created_only_from_evidence_backed_diagnosis() -> None:
    run_id = str(uuid4())
    learning = build_failure_learnings(
        {
            "id": run_id,
            "status": "failed",
            "playbook_key": "build-in-public-trend-radar",
            "events": [
                {"event_type": "incident_brief", "payload": {"worker_profile": "claim-grounding-judge"}},
                {"event_type": "run_failed", "payload": {"reason": "max_supervisor_turns exceeded"}},
            ],
        },
        {
            "root_cause": "quality_gate_failed",
            "outcome": "failed",
            "summary": "Run failed because Draft has no claims.",
            "evidence": [{"event_type": "eval_result_failed", "failure_type": "eval_failed", "error": "Draft has no claims."}],
        },
        [_proposal(run_id)],
    )[0]

    assert learning.failure_signature == "eval_failed:claim-grounding-judge"
    assert learning.target_component == "claim-grounding-judge/trend-claim-grounding"
    assert learning.occurrence_count == 1
    assert learning.first_seen_run_id == run_id
    assert learning.last_seen_run_id == run_id
    assert learning.severity == "high"
    assert learning.evidence_refs[0]["event_type"] == "eval_result_failed"


def test_recent_system_review_prioritizes_repeated_failures_and_outputs_concrete_backlog() -> None:
    run_id = str(uuid4())
    learning = build_failure_learnings(
        {"id": run_id, "status": "failed", "playbook_key": "build-in-public-trend-radar", "events": []},
        {
            "root_cause": "quality_gate_failed",
            "outcome": "failed",
            "summary": "Run failed because Draft has no claims.",
            "evidence": [{"event_type": "eval_result_failed", "failure_type": "eval_failed", "error": "Draft has no claims."}],
        },
        [_proposal(run_id)],
    )[0].model_copy(update={"occurrence_count": 3})

    review = build_recent_system_review(
        recent_runs=[{"id": run_id, "status": "failed", "playbook_key": "build-in-public-trend-radar"}],
        learnings=[learning],
        limit=20,
        playbook_key="build-in-public-trend-radar",
    )

    assert review.run_count == 1
    assert review.findings[0]["failure_signature"] == "eval_failed:claim-grounding-judge"
    assert review.findings[0]["priority"] == "p0"
    assert review.recommendations[0]["change"] == "Fix the claim-grounding contract."
    assert review.recommendations[0]["success_check"] == "Repeat a comparable real run."


def test_review_can_turn_repeated_learning_into_behavior_gated_proposal() -> None:
    run_id = str(uuid4())
    learning = build_failure_learnings(
        {"id": run_id, "status": "failed", "playbook_key": "build-in-public-trend-radar", "events": []},
        {
            "root_cause": "quality_gate_failed",
            "outcome": "failed",
            "summary": "Run failed because Draft has no claims.",
            "evidence": [{"event_type": "eval_result_failed", "failure_type": "eval_failed", "error": "Draft has no claims."}],
        },
        [_proposal(run_id)],
    )[0].model_copy(update={"occurrence_count": 2})

    proposal = proposal_from_failure_learning(learning)

    assert proposal.status == "proposed"
    assert proposal.behavior_change_requires_approval is True
    assert proposal.proof_spec["baseline_run_id"] == run_id
    assert proposal.proof_spec["expected_absent_signature"] == "eval_failed:claim-grounding-judge"
