from __future__ import annotations

from typing import Any
from uuid import UUID

from l2l3_protocol.core.schemas import FailureLearning, ImprovementProposal, SystemReview


def proof_spec_for_proposal(
    *,
    baseline_run_id: str,
    playbook_key: str | None,
    target_component: str,
    failure_signature: str,
    root_cause: str | None,
    success_check: str,
) -> dict[str, Any]:
    return {
        "real_run_required": True,
        "mocks_allowed": False,
        "fallbacks_allowed": False,
        "baseline_run_id": baseline_run_id,
        "playbook_key": playbook_key,
        "target_component": target_component,
        "failure_signature": failure_signature,
        "expected_absent_signature": failure_signature,
        "expected_absent_root_cause": root_cause,
        "success_check": success_check,
        "proof_command": f"uv run python scripts/real-before-after-proof.py --baseline-run-id {baseline_run_id}",
    }


def build_failure_learnings(
    run_state: dict[str, Any],
    diagnosis: dict[str, Any],
    proposals: list[ImprovementProposal],
) -> list[FailureLearning]:
    run_id = str(run_state["id"])
    playbook_key = str(run_state.get("playbook_key") or "") or None
    root_cause = str(diagnosis.get("root_cause") or "unknown")
    outcome = str(diagnosis.get("outcome") or run_state.get("status") or "unknown")
    summary = str(diagnosis.get("summary") or "Run diagnosis did not include a summary.")
    learnings: list[FailureLearning] = []
    for proposal in proposals:
        evidence = proposal.evidence or list(diagnosis.get("evidence", []))
        if not evidence:
            continue
        learnings.append(
            FailureLearning(
                failure_signature=proposal.failure_signature,
                target_component=proposal.target_component,
                root_cause=root_cause,
                playbook_key=playbook_key,
                proposal_type=proposal.proposal_type,
                learning_summary=summary,
                proposed_next_step=proposal.proposed_change,
                risk=proposal.risk,
                success_check=proposal.success_check,
                severity=_severity(outcome, root_cause),
                occurrence_count=1,
                first_seen_run_id=run_id,
                last_seen_run_id=run_id,
                evidence_refs=_compact_evidence(run_id, evidence),
                run_ids=[run_id],
            )
        )
    return learnings


def build_recent_system_review(
    *,
    recent_runs: list[dict[str, Any]],
    learnings: list[FailureLearning],
    limit: int,
    playbook_key: str | None = None,
) -> SystemReview:
    scoped_runs = [run for run in recent_runs if playbook_key is None or run.get("playbook_key") == playbook_key]
    scoped_learnings = [learning for learning in learnings if playbook_key is None or learning.playbook_key == playbook_key]
    ranked = sorted(scoped_learnings, key=_learning_rank, reverse=True)
    findings = [_finding_from_learning(learning) for learning in ranked[:limit]]
    recommendations = [_recommendation_from_learning(learning) for learning in ranked[:limit]]
    return SystemReview(
        playbook_key=playbook_key,
        run_count=len(scoped_runs),
        learning_count=len(scoped_learnings),
        findings=findings,
        recommendations=recommendations,
    )


def proposal_from_failure_learning(learning: FailureLearning) -> ImprovementProposal:
    proof_spec = proof_spec_for_proposal(
        baseline_run_id=learning.last_seen_run_id,
        playbook_key=learning.playbook_key,
        target_component=learning.target_component,
        failure_signature=learning.failure_signature,
        root_cause=learning.root_cause,
        success_check=learning.success_check,
    )
    return ImprovementProposal(
        run_id=UUID(learning.last_seen_run_id),
        source_run_id=learning.last_seen_run_id,
        proposal_type=learning.proposal_type,
        target_component=learning.target_component,
        failure_signature=learning.failure_signature,
        problem=f"{learning.learning_summary} Seen {learning.occurrence_count} time(s).",
        proposed_change=learning.proposed_next_step,
        risk=learning.risk,
        success_check=learning.success_check,
        evidence=learning.evidence_refs,
        behavior_change_requires_approval=True,
        proof_spec=proof_spec,
    )


def _compact_evidence(run_id: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    for item in evidence[:10]:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        refs.append(
            {
                "run_id": run_id,
                "event_type": item.get("event_type"),
                "task_id": item.get("task_id"),
                "failure_type": item.get("failure_type"),
                "worker_profile": item.get("worker_profile") or payload.get("worker_profile"),
                "eval_key": payload.get("eval_key") or item.get("eval_key"),
                "error": item.get("error"),
            }
        )
    return refs


def _severity(outcome: str, root_cause: str) -> str:
    if outcome == "failed":
        return "high"
    if root_cause in {"quality_gate_failed", "repeated_repair", "tool_or_provider_failure"}:
        return "medium"
    return "low"


def _learning_rank(learning: FailureLearning) -> tuple[int, int]:
    severity_weight = {"high": 3, "medium": 2, "low": 1}.get(learning.severity, 1)
    return (severity_weight, learning.occurrence_count)


def _priority(learning: FailureLearning) -> str:
    if learning.occurrence_count >= 3:
        return "p0"
    if learning.severity == "high" and learning.occurrence_count >= 2:
        return "p0"
    if learning.severity == "high":
        return "p1"
    if learning.occurrence_count >= 2:
        return "p1"
    return "p2"


def _finding_from_learning(learning: FailureLearning) -> dict[str, Any]:
    return {
        "priority": _priority(learning),
        "failure_signature": learning.failure_signature,
        "target_component": learning.target_component,
        "root_cause": learning.root_cause,
        "occurrence_count": learning.occurrence_count,
        "last_seen_run_id": learning.last_seen_run_id,
        "summary": learning.learning_summary,
        "evidence_refs": learning.evidence_refs,
    }


def _recommendation_from_learning(learning: FailureLearning) -> dict[str, Any]:
    return {
        "priority": _priority(learning),
        "problem": learning.learning_summary,
        "change": learning.proposed_next_step,
        "risk": learning.risk,
        "success_check": learning.success_check,
        "approval_required": True,
        "proof_spec": proof_spec_for_proposal(
            baseline_run_id=learning.last_seen_run_id,
            playbook_key=learning.playbook_key,
            target_component=learning.target_component,
            failure_signature=learning.failure_signature,
            root_cause=learning.root_cause,
            success_check=learning.success_check,
        ),
    }
