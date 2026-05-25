import json
import sys
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from typing import Any

HTTP_TIMEOUT_SECONDS = 20
USER_AGENT = "l2l3-protocol/0.1 real-trend-collector"


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
    query = require_text(contract["inputs"].get("query"), "query")
    providers = [require_text(provider, "provider").lower() for provider in require_list(contract["inputs"], "providers")]
    max_results = int(contract["inputs"].get("max_results", 5))
    if max_results < 1:
        raise WorkerInputError("max_results must be >= 1")

    allowed_toolsets = set(contract.get("allowed_tools", []))
    source_results: list[dict[str, Any]] = []
    for provider in providers:
        if provider == "github":
            _require_toolset(allowed_toolsets, "github_search", provider)
            source_results.append({"source": "github", "items": _search_github(query, max_results)})
        elif provider == "arxiv":
            _require_toolset(allowed_toolsets, "arxiv_search", provider)
            source_results.append({"source": "arxiv", "items": _search_arxiv(query, max_results)})
        elif provider in {"huggingface", "hf"}:
            _require_toolset(allowed_toolsets, "hf_hub_search", provider)
            source_results.append({"source": "huggingface", "items": _search_huggingface(query, max_results)})
        else:
            raise WorkerInputError(f"unsupported trend provider: {provider}")

    if not source_results:
        raise WorkerInputError("no trend providers were requested")
    return {"trend_signals": _normalize_trend_source_results(source_results), "source_results": source_results}


def _normalize_trend_source_results(sources: list[dict[str, Any]]) -> list[dict[str, Any]]:
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
    if not trend_signals:
        raise WorkerInputError("real trend search returned no source results")
    return trend_signals


def _require_toolset(allowed_toolsets: set[str], toolset: str, provider: str) -> None:
    if toolset not in allowed_toolsets:
        raise WorkerInputError(f"provider requires unavailable toolset: {provider} -> {toolset}")


def _request_json(url: str) -> Any:
    request = Request(url, headers={"accept": "application/json", "user-agent": USER_AGENT})
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise WorkerInputError(f"tool request failed with status {status}: {url}")
        return json.loads(response.read().decode("utf-8"))


def _request_text(url: str) -> str:
    request = Request(url, headers={"accept": "application/xml", "user-agent": USER_AGENT})
    with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
        status = getattr(response, "status", 200)
        if status >= 400:
            raise WorkerInputError(f"tool request failed with status {status}: {url}")
        return response.read().decode("utf-8")


def _search_github(query: str, max_results: int) -> list[dict[str, Any]]:
    url = "https://api.github.com/search/repositories?" + urlencode(
        {"q": query, "sort": "stars", "order": "desc", "per_page": max_results}
    )
    payload = _request_json(url)
    items = payload.get("items")
    if not isinstance(items, list):
        raise WorkerInputError("GitHub search response missing items list")
    results = []
    for item in items[:max_results]:
        results.append(
            {
                "title": require_text(item.get("full_name"), "github.full_name"),
                "url": require_text(item.get("html_url"), "github.html_url"),
                "summary": require_text(item.get("description") or item.get("full_name"), "github.description"),
                "metrics": {
                    "stars": item.get("stargazers_count", 0),
                    "forks": item.get("forks_count", 0),
                    "updated_at": item.get("updated_at"),
                },
            }
        )
    if not results:
        raise WorkerInputError(f"GitHub search returned no results for query: {query}")
    return results


def _search_arxiv(query: str, max_results: int) -> list[dict[str, Any]]:
    url = "https://export.arxiv.org/api/query?" + urlencode(
        {"search_query": f"all:{query}", "start": 0, "max_results": max_results, "sortBy": "submittedDate", "sortOrder": "descending"}
    )
    payload = _request_text(url)
    root = ET.fromstring(payload)
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    for entry in root.findall("atom:entry", namespace)[:max_results]:
        title = " ".join(entry.findtext("atom:title", default="", namespaces=namespace).split())
        summary = " ".join(entry.findtext("atom:summary", default="", namespaces=namespace).split())
        url_text = entry.findtext("atom:id", default="", namespaces=namespace)
        published = entry.findtext("atom:published", default="", namespaces=namespace)
        results.append(
            {
                "title": require_text(title, "arxiv.title"),
                "url": require_text(url_text, "arxiv.id"),
                "summary": require_text(summary, "arxiv.summary"),
                "metrics": {"published": published},
            }
        )
    if not results:
        raise WorkerInputError(f"arXiv search returned no results for query: {query}")
    return results


def _search_huggingface(query: str, max_results: int) -> list[dict[str, Any]]:
    url = "https://huggingface.co/api/models?" + urlencode({"search": query, "limit": max_results, "sort": "likes", "direction": "-1"})
    payload = _request_json(url)
    if not isinstance(payload, list):
        raise WorkerInputError("Hugging Face search response was not a list")
    results = []
    for item in payload[:max_results]:
        model_id = require_text(item.get("modelId") or item.get("id"), "huggingface.modelId")
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        results.append(
            {
                "title": model_id,
                "url": f"https://huggingface.co/{model_id}",
                "summary": f"Hugging Face model matching '{query}'. Tags: {', '.join(str(tag) for tag in tags[:8])}",
                "metrics": {"likes": item.get("likes", 0), "downloads": item.get("downloads", 0)},
            }
        )
    if not results:
        raise WorkerInputError(f"Hugging Face search returned no results for query: {query}")
    return results


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
