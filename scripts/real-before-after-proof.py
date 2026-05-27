from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


TERMINAL_OR_BLOCKED = {"completed", "failed", "cancelled", "waiting_approval", "waiting_user"}


def request_json(url: str, *, method: str = "GET", payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any] | list[Any]:
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    request = Request(url, data=data, headers={"content-type": "application/json"} if payload is not None else {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"real API request failed: {method} {url} -> {exc.code}: {body}") from exc


def require_run_with_diagnosis(api_url: str, run_id: str) -> dict[str, Any]:
    run = request_json(f"{api_url}/runs/{run_id}")
    if not isinstance(run, dict):
        raise RuntimeError(f"run fetch returned invalid payload: {run}")
    if not isinstance(run.get("diagnosis"), dict):
        raise RuntimeError(f"baseline run has no diagnosis: {run_id}")
    return run


def require_implemented_proposal(api_url: str, proposal_id: str | None, baseline_run_id: str) -> dict[str, Any]:
    if proposal_id is None:
        query = urlencode({"run_id": baseline_run_id})
        proposals = request_json(f"{api_url}/improvement-proposals?{query}")
        if not isinstance(proposals, list) or not proposals:
            raise RuntimeError(f"baseline run has no improvement proposal: {baseline_run_id}")
        proposal = proposals[0]
    else:
        proposals = request_json(f"{api_url}/improvement-proposals")
        if not isinstance(proposals, list):
            raise RuntimeError(f"proposal list returned invalid payload: {proposals}")
        proposal = next((item for item in proposals if isinstance(item, dict) and item.get("id") == proposal_id), None)
        if proposal is None:
            raise RuntimeError(f"improvement proposal not found: {proposal_id}")
    if proposal.get("status") not in {"implemented", "proven"}:
        raise RuntimeError(
            "proposal must be marked implemented or proven before before/after proof: "
            f"{proposal.get('id')} status={proposal.get('status')}"
        )
    proof_spec = proposal.get("proof_spec")
    if not isinstance(proof_spec, dict) or proof_spec.get("real_run_required") is not True:
        raise RuntimeError(f"proposal has no real-run proof spec: {proposal.get('id')}")
    return proposal


def comparable_payload(baseline: dict[str, Any], suffix: str) -> dict[str, Any]:
    run_input = baseline.get("input", {})
    if not isinstance(run_input, dict):
        raise RuntimeError("baseline run input is not an object")
    inputs = run_input.get("inputs")
    if not isinstance(inputs, dict):
        raise RuntimeError("baseline run has no input.inputs object to replay")
    return {
        "playbook_key": baseline["playbook_key"],
        "l2_mode": baseline["l2_mode"],
        "goal": f"{baseline['goal']} [{suffix}]",
        "inputs": inputs,
        "require_human_approval": bool(run_input.get("require_human_approval", True)),
    }


def wait_for_diagnosis(api_url: str, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        latest = request_json(f"{api_url}/runs/{run_id}")  # type: ignore[assignment]
        if not isinstance(latest, dict):
            raise RuntimeError(f"run fetch returned invalid payload: {latest}")
        print(
            "poll",
            run_id,
            latest.get("status"),
            "tasks",
            len(latest.get("tasks", [])),
            "evals",
            len(latest.get("evals", [])),
            "events",
            len(latest.get("events", [])),
            "diagnosis",
            bool(latest.get("diagnosis")),
            flush=True,
        )
        if latest.get("status") in TERMINAL_OR_BLOCKED and isinstance(latest.get("diagnosis"), dict):
            return latest
        time.sleep(5)
    raise RuntimeError(f"after run did not produce diagnosis before timeout: {run_id}")


def run_before_after_proof(api_url: str, baseline_run_id: str, proposal_id: str | None, timeout_seconds: int) -> dict[str, Any]:
    api_url = api_url.rstrip("/")
    health = request_json(f"{api_url}/health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError(f"real API health check failed: {health}")

    baseline = require_run_with_diagnosis(api_url, baseline_run_id)
    proposal = require_implemented_proposal(api_url, proposal_id, baseline_run_id)
    before = baseline["diagnosis"]
    proof_spec = proposal["proof_spec"]
    before_signature = proof_spec.get("expected_absent_signature") or proposal.get("failure_signature", "unknown")

    created = request_json(
        f"{api_url}/runs",
        method="POST",
        payload=comparable_payload(baseline, f"before-after proof for {proposal['id']}"),
    )
    if not isinstance(created, dict) or not created.get("id"):
        raise RuntimeError(f"real after run creation failed: {created}")
    after_run = wait_for_diagnosis(api_url, str(created["id"]), timeout_seconds)
    after = after_run["diagnosis"]
    after_proposals = after_run.get("improvement_proposals", [])
    repeated_signature = any(isinstance(item, dict) and item.get("failure_signature") == before_signature for item in after_proposals)
    if after.get("root_cause") == before.get("root_cause") and repeated_signature:
        raise RuntimeError(
            "before/after proof failed: after run repeated the implemented proposal failure "
            f"root_cause={after.get('root_cause')} signature={before_signature}"
        )
    if after.get("root_cause") not in {None, "none"}:
        raise RuntimeError(
            "before/after proof failed: after run ended with a new root cause "
            f"root_cause={after.get('root_cause')} summary={after.get('summary')}"
        )

    proof_result = {
        "status": "passed",
        "baseline_run_id": baseline_run_id,
        "after_run_id": created["id"],
        "proof_command": proof_spec.get("proof_command"),
        "before": {
            "status": baseline.get("status"),
            "root_cause": before.get("root_cause"),
            "summary": before.get("summary"),
        },
        "after": {
            "status": after_run.get("status"),
            "root_cause": after.get("root_cause"),
            "summary": after.get("summary"),
        },
    }
    proven = request_json(f"{api_url}/improvement-proposals/{proposal['id']}/mark-proven", method="POST", payload=proof_result)
    if not isinstance(proven, dict) or proven.get("status") != "proven":
        raise RuntimeError(f"proposal proof passed but mark-proven failed: {proven}")

    return {
        "baseline_run_id": baseline_run_id,
        "after_run_id": created["id"],
        "approved_proposal": {
            "id": proposal["id"],
            "proposal_type": proposal.get("proposal_type"),
            "target_component": proposal.get("target_component"),
            "failure_signature": proposal.get("failure_signature"),
            "status_after_proof": proven.get("status"),
        },
        "before": proof_result["before"],
        "after": proof_result["after"],
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real before/after proof for an approved improvement proposal.")
    parser.add_argument("--api-url", default="http://localhost:8080")
    parser.add_argument("--baseline-run-id", required=True)
    parser.add_argument("--proposal-id")
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    print(json.dumps(run_before_after_proof(args.api_url, args.baseline_run_id, args.proposal_id, args.timeout_seconds), indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
