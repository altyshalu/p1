from __future__ import annotations

from collections import defaultdict
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from l2l3_protocol.core.schemas import FailureLearning, ImprovementProposal, RegressionCase, SystemReview


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
    events = _events(run_state)
    repair_attempt_count = _repair_attempt_count(events)
    human_intervention_count = _human_intervention_count(events)
    learnings: list[FailureLearning] = []
    for proposal in proposals:
        evidence = proposal.evidence or list(diagnosis.get("evidence", []))
        evidence_refs = _compact_evidence(run_id, evidence)
        if not evidence_refs:
            continue
        learnings.append(
            FailureLearning(
                failure_signature=proposal.failure_signature,
                target_component=proposal.target_component,
                root_cause=root_cause,
                playbook_key=playbook_key,
                proposal_type=proposal.proposal_type,
                learning_summary=_concise_learning_summary(diagnosis, proposal, evidence_refs),
                proposed_next_step=proposal.proposed_change,
                risk=proposal.risk,
                success_check=proposal.success_check,
                severity=_severity(outcome, root_cause),
                occurrence_count=1,
                first_seen_run_id=run_id,
                last_seen_run_id=run_id,
                worker_family=_worker_family(proposal, evidence_refs),
                eval_family=_eval_family(proposal, evidence_refs),
                tool_family=_tool_family(proposal, evidence_refs),
                repair_attempt_count=repair_attempt_count,
                human_intervention_count=human_intervention_count,
                evidence_refs=evidence_refs,
                run_ids=[run_id],
            )
        )
    return _dedupe_learnings(learnings)


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
    top = ranked[:limit]
    return SystemReview(
        playbook_key=playbook_key,
        run_count=len(scoped_runs),
        learning_count=len(scoped_learnings),
        findings=[_finding_from_learning(learning) for learning in top],
        recommendations=[_recommendation_from_learning(learning) for learning in top],
        weak_components=_weak_components(scoped_learnings, limit),
        excess_repairs=_excess_repairs(scoped_learnings, limit),
        human_interruptions=_human_interruptions(scoped_learnings, limit),
        needed_changes=_needed_changes(scoped_learnings, limit),
        risks=_review_risks(scoped_learnings, limit),
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


def build_regression_case(
    *,
    proposal: ImprovementProposal,
    comparable_run_input: dict[str, Any],
    proof_result: dict[str, Any] | None = None,
) -> RegressionCase:
    proof_spec = proposal.proof_spec if isinstance(proposal.proof_spec, dict) else {}
    after_run_id = proof_result.get("after_run_id") if isinstance(proof_result, dict) else None
    return RegressionCase(
        proposal_id=proposal.id,
        baseline_run_id=proposal.source_run_id,
        failure_signature=proposal.failure_signature,
        target_component=proposal.target_component,
        comparable_run_input=comparable_run_input,
        proof_command=str(proof_spec.get("proof_command") or f"uv run python scripts/real-before-after-proof.py --baseline-run-id {proposal.source_run_id} --proposal-id {proposal.id}"),
        expected_absent_failure=str(proof_spec.get("expected_absent_signature") or proposal.failure_signature),
        last_after_run_id=str(after_run_id) if after_run_id else None,
        last_proof_status=str((proof_result or {}).get("status") or "pending"),
        last_proof_result=proof_result or {},
    )


def build_system_learning_report(
    *,
    active_learnings: list[FailureLearning],
    resolved_learnings: list[FailureLearning],
    proposals: list[ImprovementProposal],
    regression_cases: list[RegressionCase],
) -> dict[str, Any]:
    active = [learning for learning in active_learnings if learning.evidence_refs]
    resolved = [learning for learning in resolved_learnings if learning.evidence_refs]
    evidence_backed_proposals = [proposal for proposal in proposals if proposal.evidence]
    proposals_by_status: dict[str, list[dict[str, Any]]] = {}
    for status in ("proposed", "approved", "implemented", "proven", "rejected", "stale"):
        proposals_by_status[status] = [_proposal_report_row(p) for p in evidence_backed_proposals if p.status.value == status]
    proof_commands = sorted(
        {
            str(proposal.proof_spec.get("proof_command"))
            for proposal in evidence_backed_proposals
            if isinstance(proposal.proof_spec, dict) and proposal.proof_spec.get("proof_command")
        }
    )
    report = {
        "generated_at": datetime.now(UTC).isoformat(),
        "summary": {
            "active_learning_count": len(active),
            "resolved_learning_count": len(resolved),
            "proposal_count": len(evidence_backed_proposals),
            "regression_case_count": len(regression_cases),
        },
        "active_learnings": [_learning_report_row(learning) for learning in sorted(active, key=_learning_rank, reverse=True)],
        "resolved_learnings": [_learning_report_row(learning) for learning in sorted(resolved, key=_learning_rank, reverse=True)],
        "proposals": proposals_by_status,
        "regression_cases": [_regression_case_report_row(case) for case in regression_cases],
        "risks": _review_risks(active, 10),
        "proof_commands": proof_commands,
    }
    report["markdown"] = render_system_learning_report_markdown(report)
    return report


def render_recent_system_review_markdown(review: dict[str, Any]) -> str:
    lines = [
        "# Recent System Review",
        "",
        f"- Runs reviewed: {review.get('run_count', 0)}",
        f"- Active learnings reviewed: {review.get('learning_count', 0)}",
    ]
    playbook_key = review.get("playbook_key")
    if playbook_key:
        lines.append(f"- Playbook: `{playbook_key}`")
    lines.extend(["", "## Top repeated failures"])
    findings = review.get("findings", []) or []
    if findings:
        for finding in findings[:10]:
            lines.append(
                f"- [{finding.get('priority', 'p2').upper()}] `{finding.get('failure_signature', 'unknown')}` on `{finding.get('target_component', 'unknown')}` x{finding.get('occurrence_count', 0)}. {finding.get('summary', '')}"
            )
    else:
        lines.append("- No evidence-backed active failures found.")
    lines.extend(["", "## Weak components"])
    weak_components = review.get("weak_components", []) or []
    if weak_components:
        for component in weak_components[:10]:
            lines.append(
                f"- `{component.get('target_component', 'unknown')}`: x{component.get('occurrence_count', 0)} failures, repairs={component.get('repair_attempt_count', 0)}, human_interruptions={component.get('human_intervention_count', 0)}"
            )
    else:
        lines.append("- No weak component hotspot detected.")
    lines.extend(["", "## Excess repairs"])
    excess_repairs = review.get("excess_repairs", []) or []
    if excess_repairs:
        for item in excess_repairs[:10]:
            lines.append(
                f"- `{item.get('failure_signature', 'unknown')}` needed {item.get('repair_attempt_count', 0)} repair attempts before resolution or stop. Proposed fix: {item.get('proposed_next_step', '')}"
            )
    else:
        lines.append("- No excess repair hotspot detected.")
    lines.extend(["", "## Human interruptions"])
    interruptions = review.get("human_interruptions", []) or []
    if interruptions:
        for item in interruptions[:10]:
            lines.append(
                f"- `{item.get('failure_signature', 'unknown')}` interrupted humans {item.get('human_intervention_count', 0)} time(s). Last run: `{item.get('last_seen_run_id', 'unknown')}`"
            )
    else:
        lines.append("- No meaningful human interruption hotspot detected.")
    lines.extend(["", "## Needed changes"])
    needed_changes = review.get("needed_changes", []) or []
    if needed_changes:
        for item in needed_changes[:10]:
            lines.append(f"- {item.get('change_area', 'process')}: {item.get('count', 0)} issue(s). Example: {item.get('example_change', '')}")
    else:
        lines.append("- No extra change bucket detected.")
    lines.extend(["", "## Concrete proposed improvements"])
    recommendations = review.get("recommendations", []) or []
    if recommendations:
        for item in recommendations[:10]:
            lines.append(
                f"- [{item.get('priority', 'p2').upper()}] {item.get('change', '')} Proof: `{item.get('proof_spec', {}).get('proof_command', 'n/a')}`"
            )
    else:
        lines.append("- No concrete recommendation generated.")
    lines.extend(["", "## Risks"])
    risks = review.get("risks", []) or []
    if risks:
        for risk in risks[:10]:
            lines.append(f"- {risk}")
    else:
        lines.append("- No major unresolved risk identified.")
    return "\n".join(lines)


def render_system_learning_report_markdown(report: dict[str, Any]) -> str:
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    scope = report.get("scope", {}) if isinstance(report.get("scope"), dict) else {}
    lines = [
        "# What the system learned",
        "",
        f"- Generated at: {report.get('generated_at', 'unknown')}",
        f"- Playbook scope: {scope.get('playbook_key') or 'all'}",
        f"- Time scope (hours): {scope.get('since_hours') if scope.get('since_hours') is not None else 'all'}",
        f"- Active learnings: {summary.get('active_learning_count', 0)}",
        f"- Resolved learnings: {summary.get('resolved_learning_count', 0)}",
        f"- Evidence-backed proposals: {summary.get('proposal_count', 0)}",
        f"- Regression cases: {summary.get('regression_case_count', 0)}",
        "",
        "## Active learnings",
    ]
    active = report.get("active_learnings", []) or []
    if active:
        for item in active[:10]:
            lines.append(
                f"- `{item.get('failure_signature', 'unknown')}` on `{item.get('target_component', 'unknown')}` x{item.get('occurrence_count', 0)}. Last run: `{item.get('last_seen_run_id', 'unknown')}`"
            )
    else:
        lines.append("- No active evidence-backed learnings.")
    lines.extend(["", "## Proposal backlog"])
    proposals = report.get("proposals", {}) if isinstance(report.get("proposals"), dict) else {}
    for status in ("proposed", "approved", "implemented", "proven"):
        items = proposals.get(status, []) or []
        lines.append(f"- {status}: {len(items)}")
        for item in items[:5]:
            lines.append(
                f"- `{item.get('id', 'unknown')}` {item.get('proposal_type', 'unknown')} for `{item.get('target_component', 'unknown')}`. Proof: `{item.get('proof_command', 'n/a')}`"
            )
    lines.extend(["", "## Regression catalog"])
    regression_cases = report.get("regression_cases", []) or []
    if regression_cases:
        for item in regression_cases[:10]:
            lines.append(
                f"- Proposal `{item.get('proposal_id', 'unknown')}` guards `{item.get('failure_signature', 'unknown')}`. Last proof: {item.get('last_proof_status', 'pending')} after run `{item.get('last_after_run_id', 'n/a')}`"
            )
    else:
        lines.append("- No regression cases recorded yet.")
    lines.extend(["", "## Risks"])
    risks = report.get("risks", []) or []
    if risks:
        for risk in risks[:10]:
            lines.append(f"- {risk}")
    else:
        lines.append("- No major unresolved risk identified.")
    lines.extend(["", "## Proof commands"])
    commands = report.get("proof_commands", []) or []
    if commands:
        for command in commands[:10]:
            lines.append(f"- `{command}`")
    else:
        lines.append("- No proof command available yet.")
    return "\n".join(lines)


def _events(run_state: dict[str, Any]) -> list[dict[str, Any]]:
    return [event for event in run_state.get("events", []) if isinstance(event, dict)]


def _repair_attempt_count(events: list[dict[str, Any]]) -> int:
    return sum(1 for event in events if event.get("event_type") in {"incident_brief", "task_eval_failed", "repair_budget_exhausted"})


def _human_intervention_count(events: list[dict[str, Any]]) -> int:
    return sum(1 for event in events if event.get("event_type") in {"l2_message_user", "user_message", "run_control"})


def _compact_evidence(run_id: str, evidence: list[dict[str, Any]]) -> list[dict[str, Any]]:
    refs: list[dict[str, Any]] = []
    seen: set[tuple[Any, ...]] = set()
    for item in evidence[:20]:
        payload = item.get("payload") if isinstance(item.get("payload"), dict) else {}
        ref = {
            "run_id": run_id,
            "event_type": item.get("event_type"),
            "task_id": item.get("task_id"),
            "failure_type": item.get("failure_type"),
            "worker_profile": item.get("worker_profile") or payload.get("worker_profile"),
            "eval_key": payload.get("eval_key") or item.get("eval_key"),
            "tool_name": payload.get("tool_name") or item.get("tool_name"),
            "error": item.get("error") or payload.get("error"),
        }
        key = tuple(ref.get(field) for field in ("event_type", "task_id", "failure_type", "worker_profile", "eval_key", "tool_name", "error"))
        if key in seen:
            continue
        seen.add(key)
        refs.append(ref)
    return refs


def _severity(outcome: str, root_cause: str) -> str:
    if outcome == "failed":
        return "high"
    if root_cause in {"quality_gate_failed", "repeated_repair", "tool_or_provider_failure"}:
        return "medium"
    return "low"


def _learning_rank(learning: FailureLearning) -> tuple[int, int, int, int]:
    severity_weight = {"high": 3, "medium": 2, "low": 1}.get(learning.severity, 1)
    return (severity_weight, learning.occurrence_count, learning.repair_attempt_count, learning.human_intervention_count)


def _priority(learning: FailureLearning) -> str:
    if learning.occurrence_count >= 3 or learning.repair_attempt_count >= 4:
        return "p0"
    if learning.severity == "high" and learning.occurrence_count >= 2:
        return "p0"
    if learning.severity == "high" or learning.human_intervention_count >= 2:
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
        "worker_family": learning.worker_family,
        "eval_family": learning.eval_family,
        "tool_family": learning.tool_family,
        "occurrence_count": learning.occurrence_count,
        "repair_attempt_count": learning.repair_attempt_count,
        "human_intervention_count": learning.human_intervention_count,
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
        "evidence_refs": learning.evidence_refs,
    }


def _worker_family(proposal: ImprovementProposal, evidence_refs: list[dict[str, Any]]) -> str | None:
    for item in evidence_refs:
        worker = item.get("worker_profile")
        if isinstance(worker, str) and worker:
            return worker
    component = proposal.target_component.split("/", 1)[0].strip()
    return component or None


def _eval_family(proposal: ImprovementProposal, evidence_refs: list[dict[str, Any]]) -> str | None:
    for item in evidence_refs:
        eval_key = item.get("eval_key")
        if isinstance(eval_key, str) and eval_key:
            return eval_key
    if "/" in proposal.target_component:
        suffix = proposal.target_component.split("/", 1)[1].strip()
        return suffix or None
    return None


def _tool_family(proposal: ImprovementProposal, evidence_refs: list[dict[str, Any]]) -> str | None:
    if "provider:" in proposal.target_component:
        return proposal.target_component.split("provider:", 1)[1].strip() or None
    for item in evidence_refs:
        tool_name = item.get("tool_name")
        if isinstance(tool_name, str) and tool_name:
            return tool_name
    return None


def _concise_learning_summary(diagnosis: dict[str, Any], proposal: ImprovementProposal, evidence_refs: list[dict[str, Any]]) -> str:
    summary = str(diagnosis.get("summary") or proposal.problem or "Run diagnosis did not include a summary.").strip()
    first_error = next((str(item.get("error")).strip() for item in evidence_refs if item.get("error")), "")
    if first_error and first_error.lower() not in summary.lower():
        summary = f"{summary} Evidence: {first_error}."
    if len(summary) > 320:
        summary = f"{summary[:317].rstrip()}..."
    return summary


def _dedupe_learnings(learnings: list[FailureLearning]) -> list[FailureLearning]:
    grouped: dict[tuple[Any, ...], FailureLearning] = {}
    for learning in learnings:
        key = (
            learning.failure_signature,
            learning.target_component,
            learning.playbook_key,
            learning.root_cause,
            learning.worker_family,
            learning.eval_family,
            learning.tool_family,
        )
        existing = grouped.get(key)
        if existing is None:
            grouped[key] = learning
            continue
        existing.evidence_refs = _compact_evidence(existing.last_seen_run_id, existing.evidence_refs + learning.evidence_refs)
    return list(grouped.values())


def _weak_components(learnings: list[FailureLearning], limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"occurrence_count": 0, "repair_attempt_count": 0, "human_intervention_count": 0, "last_seen_run_id": None})
    for learning in learnings:
        bucket = grouped[learning.target_component]
        bucket["target_component"] = learning.target_component
        bucket["occurrence_count"] += learning.occurrence_count
        bucket["repair_attempt_count"] += learning.repair_attempt_count
        bucket["human_intervention_count"] += learning.human_intervention_count
        bucket["last_seen_run_id"] = learning.last_seen_run_id
    return sorted(grouped.values(), key=lambda item: (item["occurrence_count"], item["repair_attempt_count"], item["human_intervention_count"]), reverse=True)[:limit]


def _excess_repairs(learnings: list[FailureLearning], limit: int) -> list[dict[str, Any]]:
    items = [
        {
            "failure_signature": learning.failure_signature,
            "target_component": learning.target_component,
            "repair_attempt_count": learning.repair_attempt_count,
            "proposed_next_step": learning.proposed_next_step,
            "last_seen_run_id": learning.last_seen_run_id,
        }
        for learning in learnings
        if learning.repair_attempt_count >= 2
    ]
    return sorted(items, key=lambda item: item["repair_attempt_count"], reverse=True)[:limit]


def _human_interruptions(learnings: list[FailureLearning], limit: int) -> list[dict[str, Any]]:
    items = [
        {
            "failure_signature": learning.failure_signature,
            "target_component": learning.target_component,
            "human_intervention_count": learning.human_intervention_count,
            "last_seen_run_id": learning.last_seen_run_id,
        }
        for learning in learnings
        if learning.human_intervention_count >= 1
    ]
    return sorted(items, key=lambda item: item["human_intervention_count"], reverse=True)[:limit]


def _needed_changes(learnings: list[FailureLearning], limit: int) -> list[dict[str, Any]]:
    grouped: dict[str, dict[str, Any]] = defaultdict(lambda: {"count": 0, "example_change": ""})
    for learning in learnings:
        change_area = _change_area(learning)
        grouped[change_area]["change_area"] = change_area
        grouped[change_area]["count"] += learning.occurrence_count
        if not grouped[change_area]["example_change"]:
            grouped[change_area]["example_change"] = learning.proposed_next_step
    return sorted(grouped.values(), key=lambda item: item["count"], reverse=True)[:limit]


def _change_area(learning: FailureLearning) -> str:
    mapping = {
        "improve_tool": "tools",
        "improve_eval": "evals",
        "improve_playbook": "process",
        "improve_policy": "process",
    }
    return mapping.get(learning.proposal_type, "process")


def _review_risks(learnings: list[FailureLearning], limit: int) -> list[str]:
    ranked = sorted([learning for learning in learnings if learning.status.value == "active"], key=_learning_rank, reverse=True)
    return [
        f"{learning.failure_signature} still active on {learning.target_component} after {learning.occurrence_count} occurrence(s) and {learning.repair_attempt_count} repair attempt(s)."
        for learning in ranked[:limit]
    ]


def _learning_report_row(learning: FailureLearning) -> dict[str, Any]:
    return {
        "id": str(learning.id),
        "failure_signature": learning.failure_signature,
        "target_component": learning.target_component,
        "root_cause": learning.root_cause,
        "occurrence_count": learning.occurrence_count,
        "repair_attempt_count": learning.repair_attempt_count,
        "human_intervention_count": learning.human_intervention_count,
        "last_seen_run_id": learning.last_seen_run_id,
        "status": learning.status.value,
        "summary": learning.learning_summary,
        "evidence_refs": learning.evidence_refs,
        "proposed_next_step": learning.proposed_next_step,
    }


def _proposal_report_row(proposal: ImprovementProposal) -> dict[str, Any]:
    proof_spec = proposal.proof_spec if isinstance(proposal.proof_spec, dict) else {}
    implementation_result = proposal.implementation_result if isinstance(proposal.implementation_result, dict) else {}
    return {
        "id": str(proposal.id),
        "run_id": str(proposal.run_id),
        "source_run_id": proposal.source_run_id,
        "playbook_key": proof_spec.get("playbook_key"),
        "proposal_type": proposal.proposal_type,
        "target_component": proposal.target_component,
        "failure_signature": proposal.failure_signature,
        "status": proposal.status.value,
        "problem": proposal.problem,
        "proposed_change": proposal.proposed_change,
        "proof_command": proof_spec.get("proof_command"),
        "last_before_after_proof_result": implementation_result.get("last_proof_result"),
        "evidence": proposal.evidence,
    }


def _regression_case_report_row(case: RegressionCase) -> dict[str, Any]:
    comparable = case.comparable_run_input if isinstance(case.comparable_run_input, dict) else {}
    return {
        "id": str(case.id),
        "proposal_id": str(case.proposal_id),
        "baseline_run_id": case.baseline_run_id,
        "playbook_key": comparable.get("playbook_key"),
        "failure_signature": case.failure_signature,
        "target_component": case.target_component,
        "proof_command": case.proof_command,
        "expected_absent_failure": case.expected_absent_failure,
        "last_after_run_id": case.last_after_run_id,
        "last_proof_status": case.last_proof_status,
        "last_proof_result": case.last_proof_result,
    }
