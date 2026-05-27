from uuid import uuid4

import pytest

from l2l3_protocol.core.schemas import ImprovementProposal, ImprovementProposalStatus, WorkOrder
from l2l3_protocol.runtime.l3_executor import L3SandboxExecutor
from l2l3_protocol.workers.build_in_public_worker import approved_provider_auto_repairs
from l2l3_protocol.workers.proposal_implementation_worker import implement_approved_proposal


def _provider_proposal(status: ImprovementProposalStatus = ImprovementProposalStatus.APPROVED) -> ImprovementProposal:
    run_id = uuid4()
    return ImprovementProposal(
        run_id=run_id,
        source_run_id=str(run_id),
        proposal_type="improve_tool",
        target_component="trend-source-collector/provider:huggingface",
        failure_signature="provider_no_results:trend-source-collector",
        problem="Hugging Face returned no results in a real trend-radar run.",
        proposed_change="Retry approved Hugging Face resource/query variants after approval.",
        risk="Can broaden provider recall; must be proven by a comparable real run.",
        success_check="Repeat a comparable real run and verify the provider-no-results signature does not recur.",
        status=status,
    )


def _claim_grounding_proposal(status: ImprovementProposalStatus = ImprovementProposalStatus.APPROVED) -> ImprovementProposal:
    run_id = uuid4()
    return ImprovementProposal(
        run_id=run_id,
        source_run_id=str(run_id),
        proposal_type="improve_eval",
        target_component="claim-grounding-judge/trend-claim-grounding",
        failure_signature="eval_failed:claim-grounding-judge",
        problem="A real trend-radar run failed claim grounding because claims reached the eval with empty text.",
        proposed_change="Fix the claim-grounding contract between draft writer, schema normalizer, and claim-grounding judge.",
        risk="Could hide malformed upstream drafts unless proven by a comparable real run.",
        success_check="Repeat a comparable real run and verify claim-grounding no longer fails on empty claim text.",
        status=status,
    )


def test_approved_provider_auto_repairs_are_explicit_query_and_resource_attempts() -> None:
    attempts = approved_provider_auto_repairs("huggingface", "agent runtime eval memory")

    assert attempts
    assert {attempt["resource_type"] for attempt in attempts} == {"datasets", "spaces", "models"}
    assert {attempt["strategy"] for attempt in attempts} == {"approved_provider_auto_repair"}
    assert "agent runtime eval memory" in {attempt["query"] for attempt in attempts}
    assert "agent" in {attempt["query"] for attempt in attempts}


def test_implementation_worker_requires_approved_proposal() -> None:
    proposal = _provider_proposal(status=ImprovementProposalStatus.PROPOSED)

    with pytest.raises(ValueError, match="proposal must be approved"):
        implement_approved_proposal({"inputs": {"proposal": proposal.model_dump(mode="json")}}, {})


def test_implementation_worker_returns_controlled_provider_implementation_result() -> None:
    proposal = _provider_proposal()

    output = implement_approved_proposal({"inputs": {"proposal": proposal.model_dump(mode="json")}}, {})

    result = output["implementation_result"]
    assert result["status"] == "implemented"
    assert result["target_component"] == "trend-source-collector/provider:huggingface"
    assert result["proof_required"] is True
    assert result["runtime_behavior_change"]["provider"] == "huggingface"


def test_implementation_worker_returns_controlled_claim_grounding_implementation_result() -> None:
    proposal = _claim_grounding_proposal()

    output = implement_approved_proposal({"inputs": {"proposal": proposal.model_dump(mode="json")}}, {})

    result = output["implementation_result"]
    assert result["status"] == "implemented"
    assert result["target_component"] == "claim-grounding-judge/trend-claim-grounding"
    assert result["failure_signature"] == "eval_failed:claim-grounding-judge"
    assert result["proof_required"] is True
    assert result["runtime_behavior_change"]["worker"] == "draft-schema-normalizer"
    assert "No synthetic claim text" in result["runtime_behavior_change"]["disallowed_behavior"]


def test_implementation_worker_rejects_wrong_claim_grounding_proposal_type() -> None:
    proposal = _claim_grounding_proposal()
    payload = proposal.model_dump(mode="json")
    payload["proposal_type"] = "fix_code"

    with pytest.raises(ValueError, match="unsupported proposal_type for claim-grounding"):
        implement_approved_proposal({"inputs": {"proposal": payload}}, {})


@pytest.mark.asyncio
async def test_implementation_worker_runs_as_real_subprocess_worker() -> None:
    proposal = _provider_proposal()
    work_order = WorkOrder(
        run_id=uuid4(),
        task_type="implement_approved_proposal",
        goal="Implement proposal.",
        worker_profile="improvement-implementation-worker",
        worker_type="sandboxed_subprocess",
        inputs={"proposal": proposal.model_dump(mode="json")},
        output_schema={"type": "object", "required": ["implementation_result"]},
        budget={"max_seconds": 30},
    )

    output = await L3SandboxExecutor().run(
        work_order,
        {"source": "test"},
        {"entrypoint": "l2l3_protocol.workers.proposal_implementation_worker", "worker_type": "sandboxed_subprocess"},
    )

    assert output["_worker_execution"]["worker_profile"] == "improvement-implementation-worker"
    assert output["implementation_result"]["failure_signature"] == "provider_no_results:trend-source-collector"
