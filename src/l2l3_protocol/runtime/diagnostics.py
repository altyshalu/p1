from __future__ import annotations

from typing import Any
from uuid import UUID

from l2l3_protocol.core.schemas import Artifact, ArtifactType, ImprovementProposal
from l2l3_protocol.runtime.self_improvement import proof_spec_for_proposal


INTERNAL_FAILURE_TO_ROOT_CAUSE = {
    "eval_failed": "quality_gate_failed",
    "output_schema": "worker_output_contract_failed",
    "invalid_json": "worker_output_contract_failed",
    "worker_exception": "worker_execution_failed",
    "timeout": "worker_execution_failed",
    "tool_denied": "policy_or_tool_permission_failed",
    "external_action_violation": "external_action_policy_violation",
    "input_validation": "bad_or_missing_input",
    "work_order_validation": "bad_or_missing_input",
    "provider_no_results": "tool_or_provider_failure",
    "provider_request_failed": "tool_or_provider_failure",
}


def analyze_run(state: dict[str, Any]) -> tuple[Artifact, list[ImprovementProposal]]:
    run_id = str(state["id"])
    evidence = _evidence(state)
    outcome = _outcome(state)
    root_cause = _root_cause(state, evidence)
    low_quality = _low_quality_evals(state)
    repeated_repair = _repeated_repair(state)
    improvement_needed = root_cause != "none" or bool(low_quality) or repeated_repair
    summary = _summary(state, outcome, root_cause, evidence, low_quality, repeated_repair)
    diagnosis_payload = {
        "run_id": run_id,
        "playbook_key": state.get("playbook_key"),
        "outcome": outcome,
        "root_cause": root_cause,
        "summary": summary,
        "evidence": evidence,
        "low_quality_evals": low_quality,
        "repeated_repair": repeated_repair,
        "improvement_needed": improvement_needed,
        "proposal_reason": "Improvement proposal created." if improvement_needed else "No improvement proposal needed for this run.",
    }
    diagnosis = Artifact(run_id=UUID(run_id), artifact_type=ArtifactType.RUN_DIAGNOSIS, payload=diagnosis_payload)
    proposals = [_proposal_from_diagnosis(run_id, diagnosis_payload)] if improvement_needed else []
    return diagnosis, proposals


def _outcome(state: dict[str, Any]) -> str:
    status = str(state.get("status", "unknown"))
    if status == "completed":
        return "completed"
    if status == "failed":
        return "failed"
    if status == "waiting_approval":
        return "waiting_approval"
    if status == "waiting_user":
        return "waiting_user"
    if status in {"running", "created", "paused"}:
        return "stuck"
    return status


def _evidence(state: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    latest_eval_passed_by_key = _latest_eval_passed_by_key(state)
    for event in state.get("events", []):
        event_type = event.get("event_type")
        payload = event.get("payload", {})
        eval_key = _event_eval_key(event)
        if eval_key and latest_eval_passed_by_key.get(eval_key) is True:
            continue
        if event_type in {
            "incident_brief",
            "task_failed",
            "work_order_validation_failed",
            "work_order_output_validation_failed",
            "run_input_validation_failed",
            "task_eval_failed",
            "run_failed",
        }:
            items.append(
                {
                    "event_type": event_type,
                    "task_id": event.get("task_id"),
                    "failure_type": payload.get("failure_type") if isinstance(payload, dict) else None,
                    "worker_profile": payload.get("worker_profile") if isinstance(payload, dict) else None,
                    "error": payload.get("error") if isinstance(payload, dict) else None,
                    "payload": payload,
                }
            )
    for eval_result in _latest_evals_by_key(state).values():
        if eval_result.get("passed") is False:
            items.append(
                {
                    "event_type": "eval_result_failed",
                    "task_id": eval_result.get("task_id"),
                    "failure_type": "eval_failed",
                    "worker_profile": None,
                    "error": "; ".join(str(reason) for reason in eval_result.get("reasons", [])),
                    "payload": eval_result,
                }
            )
    return items


def _root_cause(state: dict[str, Any], evidence: list[dict[str, Any]]) -> str:
    run_failed_reason = _run_failed_reason(evidence)
    if run_failed_reason == "max_supervisor_turns exceeded" and _repeated_repair(state):
        return "repeated_repair"
    if _low_quality_evals(state):
        return "quality_gate_failed"
    for item in evidence:
        failure_type = str(item.get("failure_type") or "")
        if failure_type in INTERNAL_FAILURE_TO_ROOT_CAUSE:
            return INTERNAL_FAILURE_TO_ROOT_CAUSE[failure_type]
    for item in evidence:
        if item.get("event_type") == "run_failed":
            payload = item.get("payload", {})
            error_type = str(payload.get("error_type", "")) if isinstance(payload, dict) else ""
            if "KeyError" in error_type:
                return "missing_capability_or_registry_item"
            if "RuntimeError" in error_type:
                return "missing_runtime_dependency"
            return "runtime_failed"
    if evidence:
        return "runtime_failed"
    return "none"


def _run_failed_reason(evidence: list[dict[str, Any]]) -> str | None:
    for item in evidence:
        if item.get("event_type") != "run_failed":
            continue
        payload = item.get("payload", {})
        if isinstance(payload, dict):
            return str(payload.get("reason") or "")
    return None


def _low_quality_evals(state: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        {
            "eval_key": item.get("eval_key"),
            "score": item.get("score"),
            "threshold": item.get("threshold"),
            "reasons": item.get("reasons", []),
        }
        for item in _latest_evals_by_key(state).values()
        if item.get("passed") is False
    ]


def _latest_evals_by_key(state: dict[str, Any]) -> dict[str, dict[str, Any]]:
    latest: dict[str, dict[str, Any]] = {}
    for item in state.get("evals", []):
        eval_key = item.get("eval_key")
        if isinstance(eval_key, str) and eval_key:
            latest[eval_key] = item
    return latest


def _latest_eval_passed_by_key(state: dict[str, Any]) -> dict[str, bool]:
    return {key: bool(value.get("passed")) for key, value in _latest_evals_by_key(state).items()}


def _event_eval_key(event: dict[str, Any]) -> str | None:
    payload = event.get("payload", {})
    if not isinstance(payload, dict):
        return None
    eval_key = payload.get("eval_key")
    if isinstance(eval_key, str) and eval_key:
        return eval_key
    eval_result = payload.get("eval_result")
    if isinstance(eval_result, dict):
        nested_eval_key = eval_result.get("eval_key")
        if isinstance(nested_eval_key, str) and nested_eval_key:
            return nested_eval_key
    return None


def _repeated_repair(state: dict[str, Any]) -> bool:
    incident_count = sum(1 for event in state.get("events", []) if event.get("event_type") == "incident_brief")
    return incident_count >= 2


def _summary(
    state: dict[str, Any],
    outcome: str,
    root_cause: str,
    evidence: list[dict[str, Any]],
    low_quality: list[dict[str, Any]],
    repeated_repair: bool,
) -> str:
    run_failed_reason = _run_failed_reason(evidence)
    if root_cause == "repeated_repair":
        detail = f" Final failure: {run_failed_reason}." if run_failed_reason else ""
        return f"Run ended as {outcome}. Multiple repair attempts were recorded before completion.{detail}"
    if root_cause == "quality_gate_failed" and low_quality:
        keys = ", ".join(str(item.get("eval_key")) for item in low_quality)
        reasons = "; ".join(str(reason) for item in low_quality for reason in item.get("reasons", [])[:2])
        reason_detail = f" Reasons: {reasons}." if reasons else ""
        return f"Run ended as {outcome}. Root cause: {root_cause}. Failed evals: {keys}.{reason_detail}"
    if evidence:
        item = _primary_evidence(root_cause, evidence)
        worker = item.get("worker_profile") or "unknown worker"
        error = item.get("error") or item.get("failure_type") or "no error detail"
        return f"Run ended as {outcome}. Root cause: {root_cause}. Evidence points to {worker}: {error}."
    if low_quality:
        keys = ", ".join(str(item.get("eval_key")) for item in low_quality)
        return f"Run ended as {outcome}. Root cause: {root_cause}. Failed evals: {keys}."
    if repeated_repair:
        return f"Run ended as {outcome}. Multiple repair attempts were recorded."
    return f"Run ended as {outcome}. No incidents or failed evals were found."


def _primary_evidence(root_cause: str, evidence: list[dict[str, Any]]) -> dict[str, Any]:
    for item in evidence:
        failure_type = str(item.get("failure_type") or "")
        if INTERNAL_FAILURE_TO_ROOT_CAUSE.get(failure_type) == root_cause:
            return item
    for item in evidence:
        if item.get("error") or item.get("failure_type"):
            return item
    return evidence[0]


def _proposal_from_diagnosis(run_id: str, diagnosis: dict[str, Any]) -> ImprovementProposal:
    root_cause = str(diagnosis["root_cause"])
    evidence = diagnosis.get("evidence", [])
    proposal_type = _proposal_type(root_cause)
    target_component = _target_component(root_cause, evidence, diagnosis.get("low_quality_evals", []))
    failure_signature = _failure_signature(root_cause, evidence)
    success_check = "Repeat a comparable real run and verify the same root cause is absent while required evals still pass."
    return ImprovementProposal(
        run_id=UUID(run_id),
        source_run_id=run_id,
        proposal_type=proposal_type,
        target_component=target_component,
        failure_signature=failure_signature,
        problem=diagnosis["summary"],
        proposed_change=_proposed_change(root_cause, target_component, evidence, diagnosis.get("low_quality_evals", [])),
        risk="Behavior-changing improvements require explicit approval before implementation.",
        success_check=success_check,
        evidence=evidence,
        behavior_change_requires_approval=True,
        proof_spec=proof_spec_for_proposal(
            baseline_run_id=run_id,
            playbook_key=diagnosis.get("playbook_key"),
            target_component=target_component,
            failure_signature=failure_signature,
            root_cause=root_cause,
            success_check=success_check,
        ),
    )


def _target_component(root_cause: str, evidence: list[dict[str, Any]], low_quality: list[dict[str, Any]]) -> str:
    primary = _primary_evidence(root_cause, evidence) if evidence else {}
    worker = str(primary.get("worker_profile") or "unknown-worker")
    failure_type = str(primary.get("failure_type") or "")
    if root_cause == "tool_or_provider_failure":
        provider = _provider_from_evidence(primary)
        return f"trend-source-collector/provider:{provider}" if provider else "trend-source-collector/provider:unknown"
    if root_cause == "quality_gate_failed":
        eval_key = str((low_quality[0] if low_quality else {}).get("eval_key") or "unknown-eval")
        worker = worker if worker != "unknown-worker" else _worker_for_eval(eval_key)
        return f"{worker}/{eval_key}"
    if root_cause == "repeated_repair":
        return "playbook:repair-stop-rules"
    if root_cause == "policy_or_tool_permission_failed":
        return f"policy:{worker}/{failure_type or 'tool-policy'}"
    if root_cause == "bad_or_missing_input" and _is_provider_input_validation(primary):
        return "trend-radar/input.providers"
    if root_cause in {"missing_capability_or_registry_item", "missing_runtime_dependency"}:
        return f"runtime:{root_cause}"
    return worker


def _failure_signature(root_cause: str, evidence: list[dict[str, Any]]) -> str:
    if not evidence:
        return root_cause
    primary = _primary_evidence(root_cause, evidence)
    failure_type = str(primary.get("failure_type") or root_cause)
    if root_cause == "bad_or_missing_input" and _is_provider_input_validation(primary):
        return f"{failure_type}:trend-radar/input.providers"
    worker = str(primary.get("worker_profile") or "unknown-worker")
    return f"{failure_type}:{worker}"


def _is_provider_input_validation(item: dict[str, Any]) -> bool:
    payload = item.get("payload", {})
    error = item.get("error") or (payload.get("error") if isinstance(payload, dict) else "")
    return "unsupported providers requested" in str(error)


def _provider_from_evidence(item: dict[str, Any]) -> str | None:
    payload = item.get("payload", {})
    if isinstance(payload, dict):
        structured = payload.get("structured_error")
        if isinstance(structured, dict):
            failures = structured.get("provider_failures")
            if isinstance(failures, dict) and failures:
                return str(next(iter(failures))).lower()
        failures = payload.get("provider_failures")
        if isinstance(failures, dict) and failures:
            return str(next(iter(failures))).lower()
    haystack = " ".join(str(value).lower() for value in [item.get("error"), item.get("failure_type"), payload])
    for provider in ("huggingface", "github", "arxiv"):
        if provider in haystack:
            return provider
    return None


def _worker_for_eval(eval_key: str) -> str:
    if eval_key == "trend-claim-grounding":
        return "claim-grounding-judge"
    if eval_key == "trend-draft-quality":
        return "trend-draft-quality-judge"
    return "eval-worker"


def _proposal_type(root_cause: str) -> str:
    if root_cause == "tool_or_provider_failure":
        return "improve_tool"
    if root_cause in {"quality_gate_failed", "worker_output_contract_failed"}:
        return "improve_eval"
    if root_cause in {"bad_or_missing_input", "policy_or_tool_permission_failed", "external_action_policy_violation"}:
        return "improve_policy"
    if root_cause in {"missing_capability_or_registry_item", "missing_runtime_dependency"}:
        return "improve_observability"
    if root_cause == "repeated_repair":
        return "improve_playbook"
    return "fix_code"


def _proposed_change(root_cause: str, target_component: str, evidence: list[dict[str, Any]], low_quality: list[dict[str, Any]]) -> str:
    if root_cause == "tool_or_provider_failure":
        if "provider:huggingface" in target_component:
            return "Extend Hugging Face provider repair so the source collector tries approved dataset/space resource types and shorter real queries before exhausting the provider."
        if "provider:github" in target_component:
            return "Extend GitHub provider repair so the source collector generates narrower real repository queries before exhausting the provider."
        return "Improve provider repair guidance or the registered tool behavior for this real failure mode."
    if root_cause == "quality_gate_failed":
        eval_key = str((low_quality[0] if low_quality else {}).get("eval_key") or "")
        if eval_key == "trend-claim-grounding":
            return "Fix the claim-grounding contract between draft writer, schema normalizer, and claim-grounding judge so drafts preserve non-empty claims with source_url evidence."
        return "Improve the worker output or eval criteria so the required quality gate can pass on a repeated real run."
    if root_cause == "worker_output_contract_failed":
        return "Tighten worker output shaping or add an approved normalizer before the failing contract boundary."
    if root_cause == "bad_or_missing_input":
        if target_component == "trend-radar/input.providers":
            return "Validate trend-radar providers before L2 planning and reject unsupported providers explicitly instead of letting L2 route around the bad input."
        return "Make required input expectations explicit at run creation or repair the L2 Work Order construction."
    if root_cause == "policy_or_tool_permission_failed":
        return f"Align Playbook, worker, and tool policy for {target_component} so only compatible approved real tools are requested."
    if root_cause == "external_action_policy_violation":
        return "Tighten External Action policy checks and worker instructions around approval-required actions."
    if root_cause == "missing_capability_or_registry_item":
        return "Add or approve the missing Hub capability through the registry change flow."
    if root_cause == "missing_runtime_dependency":
        return "Fix the missing runtime dependency or deployment configuration required by the real path."
    if root_cause == "repeated_repair":
        return "Tighten repair limits and L2 escalation rules so repeated failed repairs become an explicit approval, policy, or worker fix decision."
    return "Investigate and implement a code fix tied to the recorded evidence."
