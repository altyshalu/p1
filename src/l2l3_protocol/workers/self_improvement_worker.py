from __future__ import annotations

import json
import sys
from typing import Any

from l2l3_protocol.core.schemas import FailureLearning
from l2l3_protocol.runtime.self_improvement import build_recent_system_review
from l2l3_protocol.workers.build_in_public_worker import WorkerInputError


def require_list(inputs: dict[str, Any], key: str) -> list[Any]:
    value = inputs.get(key)
    if not isinstance(value, list):
        raise WorkerInputError(f"missing required list input: {key}")
    return value


def review_recent_runs(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    inputs = work_order["inputs"]
    recent_runs = require_list(inputs, "recent_runs")
    raw_learnings = require_list(inputs, "failure_learnings")
    limit = int(inputs.get("limit", 50))
    if limit < 1:
        raise WorkerInputError("limit must be >= 1")
    playbook_key = inputs.get("playbook_key")
    if playbook_key is not None and not isinstance(playbook_key, str):
        raise WorkerInputError("playbook_key must be a string when provided")
    learnings = [FailureLearning.model_validate(item) for item in raw_learnings]
    review = build_recent_system_review(
        recent_runs=[item for item in recent_runs if isinstance(item, dict)],
        learnings=learnings,
        limit=limit,
        playbook_key=playbook_key,
    )
    return {"system_review": review.model_dump(mode="json")}


HANDLERS = {
    "self-improvement-reviewer": review_recent_runs,
    "review_recent_runs": review_recent_runs,
}


def main() -> None:
    request = json.loads(sys.stdin.read())
    work_order = request["work_order"]
    handler_key = work_order["worker_profile"]
    if handler_key not in HANDLERS:
        handler_key = work_order["task_type"]
    if handler_key not in HANDLERS:
        raise SystemExit(f"unknown worker_profile/task_type: {work_order['worker_profile']} / {work_order['task_type']}")
    try:
        result = HANDLERS[handler_key](work_order, request["context"])
    except WorkerInputError as exc:
        sys.stderr.write(json.dumps({"error_type": "WorkerInputError", "message": str(exc)}, ensure_ascii=True))
        raise SystemExit(2) from None
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
