import json
import sys
from typing import Any


class WorkerInputError(ValueError):
    pass


def require_list(inputs: dict[str, Any], key: str) -> list[Any]:
    value = inputs.get(key)
    if not isinstance(value, list) or not value:
        raise WorkerInputError(f"missing required non-empty list input: {key}")
    return value


def collect(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    signals = require_list(contract["inputs"], "signals")
    normalized = [{"source": "manual", "text": signal.strip(), "confidence": 1.0} for signal in signals if signal.strip()]
    if not normalized:
        raise WorkerInputError("signals contained no non-empty text")
    return {"signals": normalized}


def synthesize(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    signals = require_list(contract["inputs"], "signals")
    atoms = [
        {
            "angle": "build_update",
            "claim": signal["text"],
            "why_it_matters": "Shows concrete progress on the L2-L3 Communication Protocol.",
            "evidence": [signal["text"]],
        }
        for signal in signals
    ]
    return {"content_atoms": atoms}


def adapt(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    atoms = require_list(contract["inputs"], "atoms")
    channels = require_list(contract["inputs"], "channels")
    drafts = []
    for channel in channels:
        for atom in atoms:
            drafts.append(
                {
                    "channel": channel,
                    "status": "draft",
                    "text": f"{atom['claim']}\n\nWhy it matters: {atom['why_it_matters']}",
                    "source_angle": atom["angle"],
                }
            )
    return {"drafts": drafts}


def evaluate(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(contract["inputs"], "drafts")
    reasons: list[str] = []
    checks = {
        "has_drafts": bool(drafts),
        "all_have_channels": all(bool(draft.get("channel")) for draft in drafts),
        "all_have_text": all(bool(draft.get("text")) for draft in drafts),
        "no_publish_side_effect": all(draft.get("status") == "draft" for draft in drafts),
    }
    if not checks["has_drafts"]:
        reasons.append("No drafts were produced.")
    if not checks["all_have_text"]:
        reasons.append("One or more drafts are missing text.")
    if not checks["no_publish_side_effect"]:
        reasons.append("A draft attempted a publish side effect before approval.")
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return {"passed": all(checks.values()), "score": score, "reasons": reasons, "checks": checks}


def approve(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    require_human_approval = contract["inputs"].get("require_human_approval", True)
    return {"approval": {"status": "waiting_human" if require_human_approval else "approved_for_draft_only", "publish_allowed": False}}


def learn(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    summary = contract["inputs"].get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise WorkerInputError("missing required string input: summary")
    procedural_candidate = {
        "status": "candidate_only",
        "reason": "Procedural memory remains Git-backed and requires human review.",
        "target_registry_path": "registries/process-packs/build-in-public/process.yaml",
    }
    return {
        "memory_writes": [
            {
                "layer": "episodic",
                "content": summary.strip(),
                "metadata": {"type": "run_summary", "concepts": ["build-in-public", "L2-L3", "content"]},
            },
            {
                "layer": "semantic",
                "content": "Build-in-public drafts must stay gated until explicit human approval.",
                "metadata": {"type": "policy_learning", "concepts": ["approval", "publishing", "side-effects"]},
            },
        ],
        "procedural_change_candidate": procedural_candidate,
    }


HANDLERS = {
    "signal-collector": collect,
    "narrative-synthesizer": synthesize,
    "channel-adapter": adapt,
    "quality-judge": evaluate,
    "approval-adapter": approve,
    "learning-worker": learn,
    "collect": collect,
    "synthesize": synthesize,
    "adapt": adapt,
    "evaluate": evaluate,
    "approve": approve,
    "learn": learn,
}


def main() -> None:
    request = json.loads(sys.stdin.read())
    contract = request["contract"]
    handler_key = contract["worker_profile"]
    if handler_key not in HANDLERS:
        handler_key = contract["task_type"]
    if handler_key not in HANDLERS:
        raise SystemExit(f"unknown worker_profile/task_type: {contract['worker_profile']} / {contract['task_type']}")
    result = HANDLERS[handler_key](contract, request["context"])
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
