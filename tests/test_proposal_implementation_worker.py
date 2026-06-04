from pathlib import Path
from uuid import uuid4

import pytest

from l2l3_protocol.core.schemas import ImprovementProposal, ImprovementProposalStatus, WorkOrder
from l2l3_protocol.runtime.l3_executor import L3SandboxExecutor
from l2l3_protocol.workers.build_in_public_worker import approved_provider_auto_repairs
from l2l3_protocol.workers.proposal_implementation_worker import (
    ProposalImplementationError,
    build_autonomous_codex_plan,
    build_codex_implementer_command,
    build_codex_reviewer_command,
    check_changed_files_within_bounds,
    implement_approved_proposal,
)


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


def _autonomous_proposal(status: ImprovementProposalStatus = ImprovementProposalStatus.APPROVED) -> ImprovementProposal:
    run_id = uuid4()
    return ImprovementProposal(
        run_id=run_id,
        source_run_id=str(run_id),
        proposal_type="fix_code",
        target_component="diagnostics:auto-categories",
        failure_signature="auto:new-worker:vendor-limit-shape-changed:vendor-12345678",
        problem="A real run produced a new unknown diagnosis category.",
        proposed_change="Add a bounded regression test and fix the diagnosis grouping logic.",
        risk="Autonomous implementation must stay inside diagnostics and tests only.",
        success_check="Run diagnostics tests and verify the failure signature is stable.",
        proof_spec={
            "real_run_required": True,
            "mocks_allowed": False,
            "fallbacks_allowed": False,
            "autonomous_implementation": {
                "enabled": True,
                "allowed_paths": ["src/l2l3_protocol/runtime/diagnostics.py", "tests/test_run_diagnostics.py"],
                "forbidden_paths": ["src/l2l3_protocol/workers/p1_operator_worker.py"],
                "proof_commands": ["uv run pytest tests/test_run_diagnostics.py -q"],
            },
        },
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


def test_autonomous_codex_plan_uses_requested_default_models_and_bounds() -> None:
    proposal = _autonomous_proposal().model_dump(mode="json")
    config = proposal["proof_spec"]["autonomous_implementation"]

    plan = build_autonomous_codex_plan(proposal, config, {"repo_root": "/repo"})

    assert plan["coder_model"] == "gpt-5.5"
    assert plan["reviewer_model"] == "gpt-5.4"
    assert plan["reasoning_effort"] == "medium"
    assert plan["max_iterations"] == 3
    assert plan["auto_merge"] is False
    assert plan["require_canonical_real_proof_before_merge"] is True
    assert plan["allowed_paths"] == ["src/l2l3_protocol/runtime/diagnostics.py", "tests/test_run_diagnostics.py"]
    assert plan["proof_commands"] == ["uv run pytest tests/test_run_diagnostics.py -q"]


def test_autonomous_codex_plan_requires_bounds_and_proof_commands() -> None:
    proposal = _autonomous_proposal().model_dump(mode="json")
    config = {"enabled": True, "allowed_paths": [], "proof_commands": []}

    with pytest.raises(ProposalImplementationError, match="allowed_paths"):
        build_autonomous_codex_plan(proposal, config, {})


def test_autonomous_codex_plan_rejects_auto_merge_even_with_canonical_proof_override() -> None:
    proposal = _autonomous_proposal().model_dump(mode="json")
    config = dict(proposal["proof_spec"]["autonomous_implementation"])
    config["auto_merge"] = True
    config["require_canonical_real_proof_before_merge"] = False

    with pytest.raises(ProposalImplementationError, match="auto_merge is disabled"):
        build_autonomous_codex_plan(proposal, config, {})


def test_autonomous_codex_implementer_command_is_write_capable() -> None:
    proposal = _autonomous_proposal().model_dump(mode="json")
    config = proposal["proof_spec"]["autonomous_implementation"]
    plan = build_autonomous_codex_plan(proposal, config, {"repo_root": "/repo"})

    command = build_codex_implementer_command(plan, Path("/repo/worktree"), Path("/tmp/implementer.txt"), "fix it")

    assert command[command.index("-s") + 1] == "workspace-write"
    assert command[command.index("-m") + 1] == "gpt-5.5"


def test_autonomous_codex_reviewer_command_is_read_only() -> None:
    proposal = _autonomous_proposal().model_dump(mode="json")
    config = proposal["proof_spec"]["autonomous_implementation"]
    plan = build_autonomous_codex_plan(proposal, config, {"repo_root": "/repo"})

    command = build_codex_reviewer_command(
        plan,
        Path("/repo/worktree"),
        Path("/tmp/review-schema.json"),
        Path("/tmp/reviewer.json"),
        "review it",
    )

    assert command[command.index("-s") + 1] == "read-only"
    assert command[command.index("-m") + 1] == "gpt-5.4"


def test_autonomous_codex_worker_fails_closed_when_runtime_not_enabled(monkeypatch) -> None:
    proposal = _autonomous_proposal().model_dump(mode="json")
    monkeypatch.delenv("L2L3_ENABLE_CODEX_IMPLEMENTER", raising=False)

    with pytest.raises(ProposalImplementationError, match="L2L3_ENABLE_CODEX_IMPLEMENTER=1"):
        implement_approved_proposal({"inputs": {"proposal": proposal}}, {})


def test_autonomous_codex_bounds_check_splits_allowed_and_forbidden_files() -> None:
    result = check_changed_files_within_bounds(
        [
            "src/l2l3_protocol/runtime/diagnostics.py",
            "tests/test_run_diagnostics.py",
            "src/l2l3_protocol/workers/p1_operator_worker.py",
            "README.md",
        ],
        ["src/l2l3_protocol/runtime", "tests/test_run_diagnostics.py"],
        ["src/l2l3_protocol/workers/p1_operator_worker.py"],
    )

    assert result["ok"] is False
    assert result["violations"] == [
        {"path": "src/l2l3_protocol/workers/p1_operator_worker.py", "reason": "forbidden_path"},
        {"path": "README.md", "reason": "outside_allowed_paths"},
    ]


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
