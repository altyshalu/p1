import json
import sys
from typing import Any

from l2l3_protocol.workers.build_in_public_worker import approved_provider_auto_repairs


class ProposalImplementationError(ValueError):
    pass


def require_text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ProposalImplementationError(f"missing required non-empty string: {key}")
    return value.strip()


def implement_approved_proposal(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    proposal = work_order.get("inputs", {}).get("proposal")
    if not isinstance(proposal, dict):
        raise ProposalImplementationError("missing required object input: proposal")
    status = require_text(proposal.get("status"), "proposal.status")
    if status != "approved":
        raise ProposalImplementationError(f"proposal must be approved before implementation: status={status}")

    failure_signature = require_text(proposal.get("failure_signature"), "proposal.failure_signature")
    target_component = require_text(proposal.get("target_component"), "proposal.target_component")
    proposal_type = require_text(proposal.get("proposal_type"), "proposal.proposal_type")
    if failure_signature == "provider_no_results:trend-source-collector" and target_component.startswith(
        "trend-source-collector/provider:"
    ):
        if proposal_type != "improve_tool":
            raise ProposalImplementationError(f"unsupported proposal_type for provider implementation: {proposal_type}")
        provider = target_component.rsplit(":", 1)[-1].strip().lower()
        if provider == "hf":
            provider = "huggingface"
        sample_repairs = approved_provider_auto_repairs(provider, "agent runtime eval memory")
        if not sample_repairs:
            raise ProposalImplementationError(f"no approved provider repair strategy exists for provider: {provider}")
        return {
            "implementation_result": {
                "status": "implemented",
                "implementation_worker": "improvement-implementation-worker",
                "target_component": target_component,
                "failure_signature": failure_signature,
                "applied_change": "Enabled controlled provider retry expansion in trend-source-collector.",
                "runtime_behavior_change": {
                    "provider": provider,
                    "strategy": "When a provider returns no real results, retry approved real-query/resource variants before failing explicitly.",
                    "attempt_count_for_sample_query": len(sample_repairs) + 1,
                    "auto_repair_attempts": sample_repairs,
                },
                "approval_boundary": "Proposal status was approved before implementation.",
                "proof_required": True,
            }
        }

    if (
        failure_signature == "eval_failed:claim-grounding-judge"
        and target_component == "claim-grounding-judge/trend-claim-grounding"
    ):
        if proposal_type != "improve_eval":
            raise ProposalImplementationError(f"unsupported proposal_type for claim-grounding implementation: {proposal_type}")
        return {
            "implementation_result": {
                "status": "implemented",
                "implementation_worker": "improvement-implementation-worker",
                "target_component": target_component,
                "failure_signature": failure_signature,
                "applied_change": "Normalized trend-radar draft claims before claim-grounding so claim_text/thread-derived claims become non-empty claims[].text with real source evidence preserved.",
                "runtime_behavior_change": {
                    "worker": "draft-schema-normalizer",
                    "eval": "trend-claim-grounding",
                    "strategy": "Before claim-grounding, derive missing claim text only from existing claim_text, associated thread text, or draft text; preserve source_url/evidence_urls from prior artifacts.",
                    "disallowed_behavior": "No synthetic claim text, no synthetic source URLs, and no hidden publish/action bypass.",
                },
                "approval_boundary": "Proposal status was approved before implementation.",
                "risk": proposal.get("risk", "Claim normalization could hide malformed upstream drafts if proof is not checked on real runs."),
                "proof_required": True,
            }
        }

    raise ProposalImplementationError(
        f"no controlled implementation handler for failure_signature={failure_signature} target_component={target_component}"
    )


def main() -> None:
    request = json.loads(sys.stdin.read())
    try:
        result = implement_approved_proposal(request["work_order"], request["context"])
    except ProposalImplementationError as exc:
        sys.stderr.write(json.dumps({"error_type": "ProposalImplementationError", "message": str(exc)}, ensure_ascii=True))
        raise SystemExit(2) from None
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
