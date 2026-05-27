from __future__ import annotations

import argparse
import json
import time
from typing import Any
from urllib.error import HTTPError
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


def main() -> None:
    parser = argparse.ArgumentParser(description="Run a real build-in-public trend-radar acceptance check.")
    parser.add_argument("--api-url", default="http://localhost:8080")
    parser.add_argument("--query", default="AI agent evals runtime observability memory")
    parser.add_argument("--channel", default="x")
    parser.add_argument("--max-results", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    args = parser.parse_args()

    api_url = args.api_url.rstrip("/")
    health = request_json(f"{api_url}/health")
    if not isinstance(health, dict) or health.get("status") != "ok":
        raise RuntimeError(f"real API health check failed: {health}")

    sync = request_json(f"{api_url}/hub/sync/yaml", method="POST")
    if not isinstance(sync, dict) or int(sync.get("synced", 0)) <= 0:
        raise RuntimeError(f"real Hub sync failed: {sync}")

    run = request_json(
        f"{api_url}/runs",
        method="POST",
        payload={
            "playbook_key": "build-in-public-trend-radar",
            "l2_mode": "execution",
            "goal": "Real acceptance run for run diagnosis and improvement proposals.",
            "inputs": {
                "query": args.query,
                "providers": ["github", "arxiv", "huggingface"],
                "channels": [args.channel],
                "max_results": args.max_results,
            },
            "require_human_approval": True,
        },
    )
    if not isinstance(run, dict) or not run.get("id"):
        raise RuntimeError(f"real run creation failed: {run}")

    run_id = str(run["id"])
    deadline = time.monotonic() + args.timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        latest = request_json(f"{api_url}/runs/{run_id}")  # type: ignore[assignment]
        if not isinstance(latest, dict):
            raise RuntimeError(f"real run fetch returned invalid payload: {latest}")
        print(
            "poll",
            latest.get("status"),
            "tasks",
            len(latest.get("tasks", [])),
            "evals",
            len(latest.get("evals", [])),
            "events",
            len(latest.get("events", [])),
            "diagnosis",
            bool(latest.get("diagnosis")),
            "proposals",
            len(latest.get("improvement_proposals", [])),
            flush=True,
        )
        if latest.get("status") in TERMINAL_OR_BLOCKED and latest.get("diagnosis") is not None:
            break
        time.sleep(5)
    else:
        raise RuntimeError(f"real run did not produce diagnosis before timeout: {run_id}")

    assert latest is not None
    diagnosis = latest.get("diagnosis")
    if not isinstance(diagnosis, dict):
        raise RuntimeError(f"real run ended without diagnosis: {run_id}")
    evidence = diagnosis.get("evidence", [])
    if diagnosis.get("improvement_needed") and not latest.get("improvement_proposals"):
        raise RuntimeError(f"diagnosis required improvement but no proposal was recorded: {run_id}")
    if diagnosis.get("root_cause") != "none" and not evidence:
        raise RuntimeError(f"non-empty root cause has no recorded evidence: {run_id}")

    print(
        json.dumps(
            {
                "run_id": run_id,
                "status": latest.get("status"),
                "diagnosis": diagnosis,
                "improvement_proposals": latest.get("improvement_proposals", []),
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
