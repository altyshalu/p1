import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Any

from l2l3_protocol.workers.build_in_public_worker import approved_provider_auto_repairs


DEFAULT_CODEX_CODER_MODEL = "gpt-5.5"
DEFAULT_CODEX_REVIEWER_MODEL = "gpt-5.4"
DEFAULT_CODEX_REASONING_EFFORT = "medium"
DEFAULT_AUTONOMOUS_MAX_ITERATIONS = 3
CODEX_AUTH_ERROR_MARKERS = (
    "token_invalidated",
    "401 Unauthorized",
    "authentication token has been invalidated",
    "Please try signing in again",
    "not logged in",
    "login required",
)


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
    autonomous_config = _autonomous_config(proposal)
    if autonomous_config is not None:
        return {"implementation_result": _run_autonomous_codex_implementation(proposal, autonomous_config, context)}

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


def _autonomous_config(proposal: dict[str, Any]) -> dict[str, Any] | None:
    proof_spec = proposal.get("proof_spec")
    if not isinstance(proof_spec, dict):
        return None
    config = proof_spec.get("autonomous_implementation")
    return config if isinstance(config, dict) and config.get("enabled") is True else None


def build_autonomous_codex_plan(proposal: dict[str, Any], config: dict[str, Any], context: dict[str, Any] | None = None) -> dict[str, Any]:
    proposal_id = require_text(proposal.get("id"), "proposal.id")
    target_component = require_text(proposal.get("target_component"), "proposal.target_component")
    failure_signature = require_text(proposal.get("failure_signature"), "proposal.failure_signature")
    allowed_paths = _require_string_list(config.get("allowed_paths"), "autonomous_implementation.allowed_paths")
    proof_commands = _require_string_list(config.get("proof_commands"), "autonomous_implementation.proof_commands")
    forbidden_paths = _string_list(config.get("forbidden_paths") or [])
    max_iterations = int(config.get("max_iterations") or DEFAULT_AUTONOMOUS_MAX_ITERATIONS)
    if max_iterations < 1 or max_iterations > 5:
        raise ProposalImplementationError("autonomous_implementation.max_iterations must be between 1 and 5")
    repo_root = str(config.get("repo_root") or (context or {}).get("repo_root") or os.getcwd())
    base_branch = str(config.get("base_branch") or "main")
    branch = str(config.get("branch") or f"auto/improvement-{proposal_id[:8]}")
    worktree_root = str(config.get("worktree_root") or Path(repo_root) / ".l2l3" / "autonomous-worktrees")
    if bool(config.get("auto_merge", False)):
        raise ProposalImplementationError(
            "autonomous_implementation.auto_merge is disabled until canonical real proof is recorded"
        )
    return {
        "proposal_id": proposal_id,
        "target_component": target_component,
        "failure_signature": failure_signature,
        "repo_root": repo_root,
        "base_branch": base_branch,
        "branch": branch,
        "worktree_path": str(Path(worktree_root) / re.sub(r"[^A-Za-z0-9_.-]+", "-", branch)),
        "allowed_paths": allowed_paths,
        "forbidden_paths": forbidden_paths,
        "proof_commands": proof_commands,
        "max_iterations": max_iterations,
        "coder_model": str(config.get("coder_model") or DEFAULT_CODEX_CODER_MODEL),
        "reviewer_model": str(config.get("reviewer_model") or DEFAULT_CODEX_REVIEWER_MODEL),
        "reasoning_effort": str(config.get("reasoning_effort") or DEFAULT_CODEX_REASONING_EFFORT),
        "auto_merge": False,
        "create_pr": bool(config.get("create_pr", True)),
        "require_canonical_real_proof_before_merge": True,
    }


def _run_autonomous_codex_implementation(proposal: dict[str, Any], config: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if os.environ.get("L2L3_ENABLE_CODEX_IMPLEMENTER") != "1":
        raise ProposalImplementationError("L2L3_ENABLE_CODEX_IMPLEMENTER=1 is required for autonomous Codex implementation")
    if shutil.which("codex") is None:
        raise ProposalImplementationError("codex CLI is required for autonomous implementation")
    plan = build_autonomous_codex_plan(proposal, config, context)
    repo_root = Path(plan["repo_root"]).resolve()
    worktree_path = Path(plan["worktree_path"]).resolve()
    if not (repo_root / ".git").exists():
        raise ProposalImplementationError(f"repo_root is not a git repository: {repo_root}")
    if worktree_path.exists():
        raise ProposalImplementationError(f"autonomous worktree already exists; remove or choose another branch: {worktree_path}")

    _assert_codex_auth_ready(repo_root, plan)
    _run_command(["git", "fetch", "origin", plan["base_branch"]], cwd=repo_root, timeout=120)
    _run_command(["git", "worktree", "add", "-B", plan["branch"], str(worktree_path), f"origin/{plan['base_branch']}"], cwd=repo_root, timeout=120)
    iterations: list[dict[str, Any]] = []
    feedback = ""
    try:
        for index in range(1, int(plan["max_iterations"]) + 1):
            implementer = _run_codex_implementer(proposal, plan, worktree_path, feedback, index)
            proof_results = _run_proof_commands(plan["proof_commands"], worktree_path)
            changed_files = _changed_files(worktree_path, plan["base_branch"])
            bounds = check_changed_files_within_bounds(changed_files, plan["allowed_paths"], plan["forbidden_paths"])
            iteration = {
                "iteration": index,
                "implementer": implementer,
                "proof_results": proof_results,
                "changed_files": changed_files,
                "bounds": bounds,
            }
            if not changed_files:
                feedback = "No code or documentation changes were produced. Make the required bounded fix."
                iteration["reviewer"] = {"approved": False, "feedback": feedback}
                iterations.append(iteration)
                continue
            if not bounds["ok"]:
                feedback = f"Changed files are outside bounds: {bounds['violations']}"
                iteration["reviewer"] = {"approved": False, "feedback": feedback}
                iterations.append(iteration)
                continue
            if not all(result["returncode"] == 0 for result in proof_results):
                feedback = "Required proof commands failed. Fix the implementation and rerun proof."
                iteration["reviewer"] = {"approved": False, "feedback": feedback}
                iterations.append(iteration)
                continue
            reviewer = _run_codex_reviewer(proposal, plan, worktree_path, changed_files, proof_results, index)
            iteration["reviewer"] = reviewer
            iterations.append(iteration)
            if reviewer.get("approved") is True:
                final_changed_files = _changed_files(worktree_path, plan["base_branch"])
                final_bounds = check_changed_files_within_bounds(final_changed_files, plan["allowed_paths"], plan["forbidden_paths"])
                final_proof_results = _run_proof_commands(plan["proof_commands"], worktree_path)
                if not final_bounds["ok"]:
                    feedback = f"Final changed files are outside bounds after review: {final_bounds['violations']}"
                    iteration["final_gate"] = {"approved": False, "feedback": feedback, "bounds": final_bounds, "proof_results": final_proof_results}
                    continue
                if not all(result["returncode"] == 0 for result in final_proof_results):
                    feedback = "Final proof commands failed after review. Fix the implementation and rerun proof."
                    iteration["final_gate"] = {"approved": False, "feedback": feedback, "bounds": final_bounds, "proof_results": final_proof_results}
                    continue
                iteration["final_gate"] = {"approved": True, "bounds": final_bounds, "proof_results": final_proof_results}
                commit_sha = _commit_autonomous_changes(worktree_path, proposal)
                pr_url = _push_create_and_maybe_merge(plan, worktree_path) if plan["create_pr"] else ""
                return {
                    "status": "implemented",
                    "implementation_worker": "improvement-implementation-worker",
                    "mode": "autonomous_codex_loop",
                    "proposal_id": plan["proposal_id"],
                    "target_component": plan["target_component"],
                    "failure_signature": plan["failure_signature"],
                    "branch": plan["branch"],
                    "commit_sha": commit_sha,
                    "pr_url": pr_url,
                    "auto_merge_requested": plan["auto_merge"],
                    "canonical_real_proof_required_before_merge": plan["require_canonical_real_proof_before_merge"],
                    "models": {
                        "coder": plan["coder_model"],
                        "reviewer": plan["reviewer_model"],
                        "reasoning_effort": plan["reasoning_effort"],
                    },
                    "bounds": {
                        "allowed_paths": plan["allowed_paths"],
                        "forbidden_paths": plan["forbidden_paths"],
                    },
                    "iterations": iterations,
                    "proof_required": True,
                }
            feedback = str(reviewer.get("feedback") or "Reviewer requested changes. Address only factual blocking issues.")
        raise ProposalImplementationError(f"autonomous Codex implementation did not pass review after {plan['max_iterations']} iteration(s)")
    finally:
        if config.get("keep_worktree") is not True:
            _run_command(["git", "worktree", "remove", "--force", str(worktree_path)], cwd=repo_root, timeout=120, check=False)


def _run_codex_implementer(proposal: dict[str, Any], plan: dict[str, Any], worktree_path: Path, feedback: str, iteration: int) -> dict[str, Any]:
    output_path = Path(tempfile.mkdtemp(prefix="l2l3-codex-")) / "implementer.txt"
    prompt = _implementer_prompt(proposal, plan, feedback, iteration)
    command = build_codex_implementer_command(plan, worktree_path, output_path, prompt)
    result = _run_command(command, cwd=worktree_path, timeout=3600)
    return {"returncode": result["returncode"], "output_path": str(output_path), "stdout_tail": result["stdout_tail"], "stderr_tail": result["stderr_tail"]}


def build_codex_implementer_command(plan: dict[str, Any], worktree_path: Path, output_path: Path, prompt: str) -> list[str]:
    return [
        "codex",
        "exec",
        "-C",
        str(worktree_path),
        "-m",
        plan["coder_model"],
        "-c",
        f'model_reasoning_effort="{plan["reasoning_effort"]}"',
        "-s",
        "workspace-write",
        "--ignore-user-config",
        "--ephemeral",
        "--color",
        "never",
        "-o",
        str(output_path),
        prompt,
    ]


def _run_codex_reviewer(
    proposal: dict[str, Any],
    plan: dict[str, Any],
    worktree_path: Path,
    changed_files: list[str],
    proof_results: list[dict[str, Any]],
    iteration: int,
) -> dict[str, Any]:
    temp_dir = Path(tempfile.mkdtemp(prefix="l2l3-codex-review-"))
    output_path = temp_dir / "reviewer.json"
    schema_path = temp_dir / "review-schema.json"
    schema_path.write_text(json.dumps(codex_reviewer_output_schema()), encoding="utf-8")
    prompt = _reviewer_prompt(proposal, plan, changed_files, proof_results, iteration)
    command = build_codex_reviewer_command(plan, worktree_path, schema_path, output_path, prompt)
    result = _run_command(command, cwd=worktree_path, timeout=1800, check=False)
    if result["returncode"] != 0:
        if _codex_result_has_auth_error(result):
            _raise_codex_auth_or_runtime_error(result, "codex reviewer failed")
        return {
            "approved": False,
            "feedback": "Reviewer execution failed.",
            "blocking_findings": [result["stderr_tail"] or result["stdout_tail"]],
            "scope_ok": False,
            "proof_ok": False,
            "execution": result,
        }
    try:
        review = json.loads(output_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "approved": False,
            "feedback": f"Reviewer did not return valid structured JSON: {exc}",
            "blocking_findings": ["invalid_reviewer_output"],
            "scope_ok": False,
            "proof_ok": False,
            "execution": result,
        }
    review["execution"] = result
    return review


def build_codex_reviewer_command(
    plan: dict[str, Any],
    worktree_path: Path,
    schema_path: Path,
    output_path: Path,
    prompt: str,
) -> list[str]:
    return [
        "codex",
        "exec",
        "-C",
        str(worktree_path),
        "-m",
        plan["reviewer_model"],
        "-c",
        f'model_reasoning_effort="{plan["reasoning_effort"]}"',
        "-s",
        "read-only",
        "--ignore-user-config",
        "--ephemeral",
        "--color",
        "never",
        "--output-schema",
        str(schema_path),
        "-o",
        str(output_path),
        prompt,
    ]


def codex_reviewer_output_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "required": ["approved", "feedback", "blocking_findings", "scope_ok", "proof_ok"],
        "properties": {
            "approved": {"type": "boolean"},
            "feedback": {"type": "string"},
            "blocking_findings": {"type": "array", "items": {"type": "string"}},
            "scope_ok": {"type": "boolean"},
            "proof_ok": {"type": "boolean"},
        },
        "additionalProperties": False,
    }


def _implementer_prompt(proposal: dict[str, Any], plan: dict[str, Any], feedback: str, iteration: int) -> str:
    return (
        "You are the autonomous implementation worker for an approved L2/L3 improvement proposal.\n"
        "Stay strictly inside the declared bounds. Do not change files outside allowed paths. Do not use mocks, fallbacks, demos, or synthetic proof.\n"
        f"Iteration: {iteration}\n"
        f"Allowed paths: {plan['allowed_paths']}\n"
        f"Forbidden paths: {plan['forbidden_paths']}\n"
        f"Required proof commands: {plan['proof_commands']}\n"
        f"Proposal: {json.dumps(proposal, ensure_ascii=False)}\n"
        f"Reviewer feedback to address: {feedback or 'none'}\n"
        "Make the smallest real fix that satisfies the proposal and proof. Do not commit or push; the orchestrator handles git."
    )


def _reviewer_prompt(
    proposal: dict[str, Any],
    plan: dict[str, Any],
    changed_files: list[str],
    proof_results: list[dict[str, Any]],
    iteration: int,
) -> str:
    return (
        "You are the independent Codex reviewer for an autonomous implementation worker.\n"
        "Be factual and practical. Do not reject for style preferences or theoretical concerns. Reject only for concrete correctness, scope, safety, proof, or maintainability issues.\n"
        "Return JSON only matching the schema.\n"
        f"Iteration: {iteration}\n"
        f"Allowed paths: {plan['allowed_paths']}\n"
        f"Forbidden paths: {plan['forbidden_paths']}\n"
        f"Changed files: {changed_files}\n"
        f"Proof results: {json.dumps(proof_results, ensure_ascii=False)}\n"
        f"Proposal: {json.dumps(proposal, ensure_ascii=False)}\n"
        "Approve only if the diff stays within bounds, the proposal is actually addressed, and required proof passed."
    )


def _assert_codex_auth_ready(repo_root: Path, plan: dict[str, Any]) -> None:
    status = _run_command(["codex", "login", "status"], cwd=repo_root, timeout=30, check=False)
    status_output = f"{status['stdout']}\n{status['stderr']}"
    if status["returncode"] != 0 or "Logged in" not in status_output:
        raise ProposalImplementationError(
            "codex auth is not ready. Run `codex login --device-auth` and complete the browser login before using autonomous implementation."
        )
    output_path = Path(tempfile.mkdtemp(prefix="l2l3-codex-auth-")) / "auth-check.txt"
    result = _run_command(
        [
            "codex",
            "exec",
            "-C",
            str(repo_root),
            "-m",
            plan["coder_model"],
            "-c",
            f'model_reasoning_effort="{plan["reasoning_effort"]}"',
            "-s",
            "read-only",
            "--ignore-user-config",
            "--ephemeral",
            "--color",
            "never",
            "-o",
            str(output_path),
            "Reply exactly: CODEX_AUTH_READY",
        ],
        cwd=repo_root,
        timeout=180,
        check=False,
    )
    if result["returncode"] != 0:
        _raise_codex_auth_or_runtime_error(result, "codex auth readiness check failed")
    try:
        response = output_path.read_text(encoding="utf-8").strip()
    except OSError as exc:
        raise ProposalImplementationError(f"codex auth readiness check did not write output: {exc}") from exc
    if response != "CODEX_AUTH_READY":
        raise ProposalImplementationError(f"codex auth readiness check returned unexpected output: {response[:200]}")


def _run_proof_commands(commands: list[str], cwd: Path) -> list[dict[str, Any]]:
    return [_run_command(command, cwd=cwd, timeout=1800, shell=True, check=False) for command in commands]


def _changed_files(worktree_path: Path, base_branch: str) -> list[str]:
    _run_command(["git", "add", "-N", "."], cwd=worktree_path, timeout=120, check=False)
    result = _run_command(["git", "diff", "--name-only", f"origin/{base_branch}"], cwd=worktree_path, timeout=120)
    files = [line.strip() for line in result["stdout"].splitlines() if line.strip()]
    return sorted(set(files))


def check_changed_files_within_bounds(changed_files: list[str], allowed_paths: list[str], forbidden_paths: list[str]) -> dict[str, Any]:
    violations: list[dict[str, str]] = []
    for path in changed_files:
        if any(_path_matches(path, forbidden) for forbidden in forbidden_paths):
            violations.append({"path": path, "reason": "forbidden_path"})
            continue
        if not any(_path_matches(path, allowed) for allowed in allowed_paths):
            violations.append({"path": path, "reason": "outside_allowed_paths"})
    return {"ok": not violations, "violations": violations}


def _path_matches(path: str, boundary: str) -> bool:
    normalized = path.strip().strip("/")
    boundary = boundary.strip().strip("/")
    return normalized == boundary or normalized.startswith(f"{boundary}/")


def _commit_autonomous_changes(worktree_path: Path, proposal: dict[str, Any]) -> str:
    _run_command(["git", "add", "."], cwd=worktree_path, timeout=120)
    message = f"fix(self-improvement): implement proposal {str(proposal.get('id'))[:8]}"
    _run_command(["git", "commit", "-m", message], cwd=worktree_path, timeout=120)
    result = _run_command(["git", "rev-parse", "HEAD"], cwd=worktree_path, timeout=120)
    return result["stdout"].strip()


def _push_create_and_maybe_merge(plan: dict[str, Any], worktree_path: Path) -> str:
    if plan["auto_merge"]:
        raise ProposalImplementationError("autonomous auto_merge is disabled until canonical real proof is recorded")
    _run_command(["git", "push", "-u", "origin", plan["branch"]], cwd=worktree_path, timeout=300)
    if shutil.which("gh") is None:
        raise ProposalImplementationError("gh CLI is required to create or merge autonomous PRs")
    title = f"fix(self-improvement): implement proposal {plan['proposal_id'][:8]}"
    body = (
        "Autonomous implementation worker output.\n\n"
        f"- Proposal: `{plan['proposal_id']}`\n"
        f"- Target: `{plan['target_component']}`\n"
        f"- Proof commands: `{plan['proof_commands']}`\n"
    )
    result = _run_command(
        ["gh", "pr", "create", "--base", plan["base_branch"], "--head", plan["branch"], "--title", title, "--body", body],
        cwd=worktree_path,
        timeout=300,
    )
    pr_url = result["stdout"].strip().splitlines()[-1]
    return pr_url


def _run_command(
    command: list[str] | str,
    *,
    cwd: Path,
    timeout: int,
    shell: bool = False,
    check: bool = True,
) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=str(cwd),
            timeout=timeout,
            shell=shell,
            text=True,
            input="",
            capture_output=True,
            env={**os.environ, "TERM": os.environ.get("TERM") or "xterm-256color"},
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        stderr = exc.stderr if isinstance(exc.stderr, str) else ""
        result = {
            "command": command if isinstance(command, str) else " ".join(command),
            "returncode": 124,
            "stdout": stdout,
            "stderr": stderr,
            "stdout_tail": stdout[-4000:],
            "stderr_tail": stderr[-4000:],
        }
        if _is_codex_command(command):
            _raise_codex_auth_or_runtime_error(result, "codex command timed out")
        if check:
            raise ProposalImplementationError(f"command timed out: {result['command']}\n{result['stderr_tail'] or result['stdout_tail']}") from exc
        return result
    result = {
        "command": command if isinstance(command, str) else " ".join(command),
        "returncode": completed.returncode,
        "stdout": completed.stdout,
        "stderr": completed.stderr,
        "stdout_tail": completed.stdout[-4000:],
        "stderr_tail": completed.stderr[-4000:],
    }
    if check and completed.returncode != 0:
        if _is_codex_command(command):
            _raise_codex_auth_or_runtime_error(result, "codex command failed")
        raise ProposalImplementationError(f"command failed: {result['command']}\n{result['stderr_tail'] or result['stdout_tail']}")
    return result


def _is_codex_command(command: list[str] | str) -> bool:
    if isinstance(command, str):
        return command.strip().startswith("codex ")
    return bool(command) and command[0] == "codex"


def _raise_codex_auth_or_runtime_error(result: dict[str, Any], prefix: str) -> None:
    if _codex_result_has_auth_error(result):
        raise ProposalImplementationError(
            f"{prefix}: Codex credentials are missing, expired, or invalid. "
            "Run `codex logout` and then `codex login --device-auth`, complete the browser login, and retry.\n"
            f"{result.get('stderr_tail') or result.get('stdout_tail')}"
        )
    raise ProposalImplementationError(f"{prefix}: {result['command']}\n{result['stderr_tail'] or result['stdout_tail']}")


def _codex_result_has_auth_error(result: dict[str, Any]) -> bool:
    combined = f"{result.get('stderr', '')}\n{result.get('stdout', '')}"
    return any(marker.lower() in combined.lower() for marker in CODEX_AUTH_ERROR_MARKERS)


def _require_string_list(value: Any, key: str) -> list[str]:
    items = _string_list(value)
    if not items:
        raise ProposalImplementationError(f"missing required non-empty string list: {key}")
    return items


def _string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [str(item).strip() for item in value if str(item).strip()]


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
