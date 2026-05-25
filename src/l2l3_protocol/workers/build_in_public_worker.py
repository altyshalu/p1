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


def require_text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise WorkerInputError(f"missing required non-empty string: {key}")
    return value.strip()


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


def collect_trend_sources(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    sources = require_list(contract["inputs"], "sources")
    trend_signals: list[dict[str, Any]] = []
    for source_group in sources:
        source = require_text(source_group.get("source"), "source")
        items = source_group.get("items")
        if not isinstance(items, list) or not items:
            raise WorkerInputError(f"source group has no items: {source}")
        for item in items:
            title = require_text(item.get("title"), "title")
            url = require_text(item.get("url"), "url")
            summary = require_text(item.get("summary"), "summary")
            metrics = item.get("metrics")
            if not isinstance(metrics, dict):
                raise WorkerInputError(f"trend item metrics must be an object: {title}")
            trend_signals.append({"source": source, "title": title, "url": url, "summary": summary, "metrics": metrics})
    return {"trend_signals": trend_signals}


def deduplicate_trends(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    trend_signals = require_list(contract["inputs"], "trend_signals")
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for signal in trend_signals:
        title = require_text(signal.get("title"), "title")
        url = require_text(signal.get("url"), "url")
        key = url.lower() if url else title.lower()
        if key in seen:
            continue
        seen.add(key)
        deduped.append(signal)
    if not deduped:
        raise WorkerInputError("all trend signals were duplicates")
    return {"deduped_signals": deduped}


def score_relevance(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    deduped_signals = require_list(contract["inputs"], "deduped_signals")
    themes = [require_text(theme, "theme").lower() for theme in require_list(contract["inputs"], "themes")]
    ranked = []
    for signal in deduped_signals:
        text = f"{signal.get('title', '')} {signal.get('summary', '')}".lower()
        matches = [theme for theme in themes if theme.lower() in text]
        score = min(1.0, 0.35 + 0.15 * len(matches))
        ranked.append({**signal, "score": round(score, 2), "reasons": [f"matched theme: {theme}" for theme in matches]})
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return {"ranked_signals": ranked}


SLOP_PHRASES = [
    "game-changing",
    "unlock",
    "delve",
    "seamless",
    "robust",
    "cutting-edge",
    "revolutionize",
    "in today's fast-paced",
]


def stop_slop_edit(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(contract["inputs"], "drafts")
    edited = []
    for draft in drafts:
        text = require_text(draft.get("text"), "draft.text")
        cleaned = text
        for phrase in SLOP_PHRASES:
            cleaned = cleaned.replace(phrase, "").replace(phrase.title(), "")
        cleaned = " ".join(cleaned.split())
        edited.append({**draft, "text": cleaned, "edit_notes": ["Removed predictable AI writing patterns."]})
    return {"edited_drafts": edited}


def claim_grounding(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(contract["inputs"], "drafts")
    checks = {"has_claims": True, "every_claim_has_source_url": True, "no_empty_claim_text": True}
    reasons: list[str] = []
    for draft in drafts:
        claims = draft.get("claims")
        if not isinstance(claims, list) or not claims:
            checks["has_claims"] = False
            reasons.append("Draft has no claims.")
            continue
        for claim in claims:
            if not isinstance(claim.get("text"), str) or not claim["text"].strip():
                checks["no_empty_claim_text"] = False
                reasons.append("A claim has empty text.")
            if not isinstance(claim.get("source_url"), str) or not claim["source_url"].strip():
                checks["every_claim_has_source_url"] = False
                reasons.append("A claim is missing source_url.")
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return {"passed": all(checks.values()), "score": score, "reasons": reasons, "checks": checks}


def trend_quality(contract: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(contract["inputs"], "drafts")
    checks = {
        "has_drafts": bool(drafts),
        "all_have_channels": all(bool(draft.get("channel")) for draft in drafts),
        "all_have_text": all(bool(draft.get("text")) for draft in drafts),
        "no_publish_side_effect": all(draft.get("status") == "draft" for draft in drafts),
        "no_slop_phrases": all(not any(phrase in draft.get("text", "").lower() for phrase in SLOP_PHRASES) for draft in drafts),
    }
    reasons = [check for check, passed in checks.items() if not passed]
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return {"passed": all(checks.values()), "score": score, "reasons": reasons, "checks": checks}


HANDLERS = {
    "signal-collector": collect,
    "narrative-synthesizer": synthesize,
    "channel-adapter": adapt,
    "quality-judge": evaluate,
    "approval-adapter": approve,
    "learning-worker": learn,
    "trend-source-collector": collect_trend_sources,
    "trend-deduplicator": deduplicate_trends,
    "relevance-scorer": score_relevance,
    "stop-slop-editor": stop_slop_edit,
    "claim-grounding-judge": claim_grounding,
    "trend-draft-quality-judge": trend_quality,
    "collect": collect,
    "synthesize": synthesize,
    "adapt": adapt,
    "evaluate": evaluate,
    "approve": approve,
    "learn": learn,
    "collect_trend_sources": collect_trend_sources,
    "deduplicate_trends": deduplicate_trends,
    "score_relevance": score_relevance,
    "stop_slop_edit": stop_slop_edit,
    "claim_grounding": claim_grounding,
    "trend_quality": trend_quality,
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
