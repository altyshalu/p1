import json
import re
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
import xml.etree.ElementTree as ET
from typing import Any

HTTP_TIMEOUT_SECONDS = 8
HTTP_RETRY_DELAYS_SECONDS = (3,)
HTTP_RATE_LIMIT_RETRY_SECONDS = 30
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


def collect(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    signals = require_list(work_order["inputs"], "signals")
    normalized = [{"source": "manual", "text": signal.strip(), "confidence": 1.0} for signal in signals if signal.strip()]
    if not normalized:
        raise WorkerInputError("signals contained no non-empty text")
    return {"signals": normalized}


def synthesize(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    signals = require_list(work_order["inputs"], "signals")
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


def adapt(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    atoms = require_list(work_order["inputs"], "atoms")
    channels = require_list(work_order["inputs"], "channels")
    drafts = []
    for channel in channels:
        for atom in atoms:
            if isinstance(atom, str) and atom.strip():
                drafts.append(
                    {
                        "channel": channel,
                        "status": "draft",
                        "text": atom.strip(),
                        "source_angle": "generic",
                    }
                )
                continue
            if not isinstance(atom, dict):
                raise WorkerInputError("atoms must contain strings or objects")
            headline = _first_text(atom, "claim", "headline", "title", "source_signal")
            detail = _first_text(atom, "why_it_matters", "body", "summary", "description")
            text_value = _first_text(atom, "text")
            if text_value is None:
                if headline is None and detail is None:
                    raise WorkerInputError("atom is missing claim/headline/text fields")
                if headline is None:
                    text_value = detail
                elif detail is None:
                    text_value = headline
                else:
                    text_value = f"{headline}\n\nWhy it matters: {detail}"
            drafts.append(
                {
                    "channel": channel,
                    "status": "draft",
                    "text": text_value,
                    "source_angle": _first_text(atom, "angle", "type", "kind", default="generic"),
                }
            )
    return {"drafts": drafts}


def _first_text(item: dict[str, Any], *keys: str, default: str | None = None) -> str | None:
    for key in keys:
        value = item.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return default


def evaluate(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(work_order["inputs"], "drafts")
    reasons: list[str] = []
    checks = {
        "has_drafts": bool(drafts),
        "all_have_channels": all(bool(draft.get("channel")) for draft in drafts),
        "all_have_text": all(bool(draft.get("text")) for draft in drafts),
        "no_publish_external_action": all(draft.get("status") == "draft" for draft in drafts),
    }
    if not checks["has_drafts"]:
        reasons.append("No drafts were produced.")
    if not checks["all_have_text"]:
        reasons.append("One or more drafts are missing text.")
    if not checks["no_publish_external_action"]:
        reasons.append("A draft attempted a publish External Action before approval.")
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return {"passed": all(checks.values()), "score": score, "reasons": reasons, "checks": checks}


def approve(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    require_human_approval = work_order["inputs"].get("require_human_approval", True)
    return {"approval": {"status": "waiting_human" if require_human_approval else "approved_for_draft_only", "publish_allowed": False}}


def learn(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    summary = work_order["inputs"].get("summary")
    if not isinstance(summary, str) or not summary.strip():
        raise WorkerInputError("missing required string input: summary")
    procedural_candidate = {
        "status": "candidate_only",
        "reason": "Procedural memory remains Git-backed and requires human review.",
        "target_registry_path": "registries/playbooks/build-in-public/playbook.yaml",
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
                "metadata": {"type": "policy_learning", "concepts": ["approval", "publishing", "external-actions"]},
            },
        ],
        "procedural_change_candidate": procedural_candidate,
    }


def collect_trend_sources(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    query = require_text(work_order["inputs"].get("query"), "query")
    providers = [require_text(provider, "provider").lower() for provider in require_list(work_order["inputs"], "providers")]
    max_results = int(work_order["inputs"].get("max_results", 5))
    if max_results < 1:
        raise WorkerInputError("max_results must be >= 1")

    provider_repairs = _provider_repairs(work_order["inputs"].get("provider_repairs", {}))
    approved_auto_repairs = _approved_auto_repair_providers(work_order["inputs"].get("approved_provider_auto_repairs", {}))
    allowed_toolsets = set(work_order.get("allowed_tools", []))
    source_results: list[dict[str, Any]] = []
    provider_attempts: dict[str, list[dict[str, Any]]] = {}
    provider_failures: dict[str, str] = {}
    for provider in providers:
        normalized_provider = "huggingface" if provider == "hf" else provider
        try:
            items, attempts = _search_provider_with_l2_repairs(
                normalized_provider,
                query,
                max_results,
                allowed_toolsets,
                provider_repairs,
                normalized_provider in approved_auto_repairs,
            )
            source_results.append({"source": normalized_provider, "items": items})
            provider_attempts[normalized_provider] = attempts
        except WorkerInputError as exc:
            provider_attempts[normalized_provider] = getattr(exc, "attempts", [])
            provider_failures[normalized_provider] = str(exc)

    if not source_results:
        failure = WorkerInputError(f"all trend providers failed: {provider_failures}")
        failure.provider_failures = provider_failures
        failure.provider_attempts = provider_attempts
        raise failure
    if provider_failures:
        failure = WorkerInputError(f"trend providers failed: {provider_failures}")
        failure.provider_failures = provider_failures
        failure.provider_attempts = provider_attempts
        raise failure
    return {
        "trend_signals": _normalize_trend_source_results(source_results),
        "source_results": source_results,
        "provider_attempts": provider_attempts,
    }


def _provider_repairs(value: Any) -> dict[str, list[dict[str, Any]]]:
    if value is None or value == {}:
        return {}
    if not isinstance(value, dict):
        raise WorkerInputError("provider_repairs must be an object")
    repairs: dict[str, list[dict[str, Any]]] = {}
    for provider, attempts in value.items():
        normalized_provider = require_text(provider, "provider_repairs.provider").lower()
        if normalized_provider == "hf":
            normalized_provider = "huggingface"
        if not isinstance(attempts, list) or not attempts:
            raise WorkerInputError(f"provider_repairs.{provider} must be a non-empty list")
        repairs[normalized_provider] = []
        for index, attempt in enumerate(attempts):
            if not isinstance(attempt, dict):
                raise WorkerInputError(f"provider_repairs.{provider}[{index}] must be an object")
            repair_query = require_text(attempt.get("query"), f"provider_repairs.{provider}[{index}].query")
            strategy = require_text(attempt.get("strategy", "l2_selected_query"), f"provider_repairs.{provider}[{index}].strategy")
            resource_type = attempt.get("resource_type")
            repairs[normalized_provider].append(
                {
                    "query": repair_query,
                    "strategy": strategy,
                    "resource_type": require_text(resource_type, f"provider_repairs.{provider}[{index}].resource_type")
                    if resource_type is not None
                    else None,
                }
            )
    return repairs


def _approved_auto_repair_providers(value: Any) -> set[str]:
    if value is None or value == {}:
        return set()
    if value is True:
        return {"github", "arxiv", "huggingface"}
    if not isinstance(value, dict):
        raise WorkerInputError("approved_provider_auto_repairs must be an object or true")
    raw_providers = value.get("providers")
    if not isinstance(raw_providers, list) or not raw_providers:
        raise WorkerInputError("approved_provider_auto_repairs.providers must be a non-empty list")
    providers = set()
    for provider in raw_providers:
        normalized_provider = require_text(provider, "approved_provider_auto_repairs.providers[]").lower()
        providers.add("huggingface" if normalized_provider == "hf" else normalized_provider)
    return providers


def _search_provider_with_l2_repairs(
    provider: str,
    query: str,
    max_results: int,
    allowed_toolsets: set[str],
    provider_repairs: dict[str, list[dict[str, Any]]],
    approved_auto_repairs: bool = False,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    attempts = [{"query": query, "strategy": "initial", "resource_type": _default_resource_type(provider)}]
    attempts.extend(provider_repairs.get(provider, []))
    if approved_auto_repairs:
        attempts.extend(approved_provider_auto_repairs(provider, query))
    attempts = _dedupe_provider_attempts(attempts)
    attempted: list[dict[str, Any]] = []
    errors: list[str] = []
    for attempt in attempts:
        attempt = dict(attempt)
        attempted.append(attempt)
        attempt_query = require_text(attempt.get("query"), "repair.query")
        resource_type = attempt.get("resource_type") or _default_resource_type(provider)
        try:
            items = _search_provider(provider, attempt_query, max_results, allowed_toolsets, str(resource_type))
        except WorkerInputError as exc:
            attempt["status"] = "failed"
            attempt["error"] = str(exc)
            errors.append(str(exc))
            continue
        attempt["status"] = "ok"
        attempt["result_count"] = len(items)
        return items, attempted
    error = WorkerInputError(f"{provider} search failed after {len(attempts)} real attempts: {errors}")
    error.attempts = attempted
    raise error


def approved_provider_auto_repairs(provider: str, query: str) -> list[dict[str, Any]]:
    normalized_provider = "huggingface" if provider == "hf" else provider.lower()
    variants = _query_variants(query)
    attempts: list[dict[str, Any]] = []
    if normalized_provider == "huggingface":
        for resource_type in ("datasets", "spaces", "models"):
            for variant in variants:
                attempts.append({"query": variant, "strategy": "approved_provider_auto_repair", "resource_type": resource_type})
        return _dedupe_provider_attempts(attempts)
    if normalized_provider == "github":
        return [
            {"query": variant, "strategy": "approved_provider_auto_repair", "resource_type": "repositories"}
            for variant in variants
        ]
    if normalized_provider == "arxiv":
        return [{"query": variant, "strategy": "approved_provider_auto_repair", "resource_type": "papers"} for variant in variants]
    return []


def _query_variants(query: str) -> list[str]:
    clean = " ".join(require_text(query, "query").replace("/", " ").replace("_", " ").split())
    tokens = [token for token in re.split(r"\s+", clean) if token]
    variants: list[str] = [clean]
    for length in (4, 3, 2, 1):
        if len(tokens) >= length:
            variants.append(" ".join(tokens[:length]))
    return [variant for variant in dict.fromkeys(variants) if variant]


def _dedupe_provider_attempts(attempts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    deduped: list[dict[str, Any]] = []
    seen: set[tuple[str, str, str]] = set()
    for attempt in attempts:
        query = str(attempt.get("query") or "").strip()
        resource_type = str(attempt.get("resource_type") or "").strip()
        key = (query.lower(), resource_type.lower(), "")
        if not query or key in seen:
            continue
        seen.add(key)
        deduped.append(attempt)
    return deduped


def _default_resource_type(provider: str) -> str:
    return {"github": "repositories", "arxiv": "papers", "huggingface": "models"}.get(provider, "unknown")


def _search_provider(provider: str, query: str, max_results: int, allowed_toolsets: set[str], resource_type: str) -> list[dict[str, Any]]:
    if provider == "github":
        _require_toolset(allowed_toolsets, "github_search", provider)
        return _search_github(query, max_results)
    if provider == "arxiv":
        _require_toolset(allowed_toolsets, "arxiv_search", provider)
        return _search_arxiv(query, max_results)
    if provider == "huggingface":
        _require_toolset(allowed_toolsets, "hf_hub_search", provider)
        return _search_huggingface(query, max_results, resource_type)
    raise WorkerInputError(f"unsupported trend provider: {provider}")


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
    payload = _request_bytes(url, accept="application/json")
    return json.loads(payload.decode("utf-8"))


def _request_text(url: str) -> str:
    return _request_bytes(url, accept="application/xml").decode("utf-8")


def _request_bytes(url: str, *, accept: str) -> bytes:
    request = Request(url, headers={"accept": accept, "user-agent": USER_AGENT})
    for attempt in range(len(HTTP_RETRY_DELAYS_SECONDS) + 1):
        try:
            with urlopen(request, timeout=HTTP_TIMEOUT_SECONDS) as response:
                status = getattr(response, "status", 200)
                if status >= 400:
                    raise WorkerInputError(f"tool request failed with status {status}: {url}")
                return response.read()
        except HTTPError as exc:
            if exc.code == 429 and attempt < len(HTTP_RETRY_DELAYS_SECONDS):
                time.sleep(_retry_delay_seconds(exc, attempt))
                continue
            body = exc.read().decode("utf-8", errors="replace")[:300]
            raise WorkerInputError(f"tool request failed with status {exc.code}: {url}: {body}") from exc
        except TimeoutError as exc:
            if attempt < len(HTTP_RETRY_DELAYS_SECONDS):
                time.sleep(HTTP_RETRY_DELAYS_SECONDS[attempt])
                continue
            raise WorkerInputError(f"tool request timed out after {HTTP_TIMEOUT_SECONDS}s: {url}") from exc
        except URLError as exc:
            raise WorkerInputError(f"tool request failed: {url}: {exc.reason}") from exc
    raise WorkerInputError(f"tool request failed after retries: {url}")


def _retry_delay_seconds(exc: HTTPError, attempt: int) -> int:
    retry_after = exc.headers.get("Retry-After") if exc.headers is not None else None
    if retry_after is not None:
        try:
            parsed = int(str(retry_after).strip())
        except ValueError:
            parsed = 0
        if parsed > 0:
            return min(parsed, HTTP_RATE_LIMIT_RETRY_SECONDS)
    return HTTP_RATE_LIMIT_RETRY_SECONDS


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


def _search_huggingface(query: str, max_results: int, resource_type: str = "models") -> list[dict[str, Any]]:
    if resource_type == "models":
        path = "models"
    elif resource_type == "datasets":
        path = "datasets"
    elif resource_type == "spaces":
        path = "spaces"
    else:
        raise WorkerInputError(f"unsupported Hugging Face resource_type: {resource_type}")
    url = f"https://huggingface.co/api/{path}?" + urlencode({"search": query, "limit": max_results, "sort": "likes", "direction": "-1"})
    payload = _request_json(url)
    if not isinstance(payload, list):
        raise WorkerInputError("Hugging Face search response was not a list")
    results = []
    for item in payload[:max_results]:
        item_id = require_text(item.get("modelId") or item.get("id"), "huggingface.id")
        tags = item.get("tags") if isinstance(item.get("tags"), list) else []
        results.append(
            {
                "title": item_id,
                "url": f"https://huggingface.co/{'datasets/' if resource_type == 'datasets' else 'spaces/' if resource_type == 'spaces' else ''}{item_id}",
                "summary": f"Hugging Face {resource_type.rstrip('s')} matching '{query}'. Tags: {', '.join(str(tag) for tag in tags[:8])}",
                "metrics": {"likes": item.get("likes", 0), "downloads": item.get("downloads", 0)},
            }
        )
    if not results:
        raise WorkerInputError(f"Hugging Face {resource_type} search returned no results for query: {query}")
    return results


def deduplicate_trends(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    trend_signals = require_list(work_order["inputs"], "trend_signals")
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


def score_relevance(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    deduped_signals = require_list(work_order["inputs"], "deduped_signals")
    themes = [require_text(theme, "theme").lower() for theme in require_list(work_order["inputs"], "themes")]
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
URL_PATTERN = re.compile(r"https?://[^\s)>\]}]+")


def stop_slop_edit(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(work_order["inputs"], "drafts")
    edited = []
    for draft in drafts:
        normalized_draft = _normalize_draft_shape(draft)
        text = require_text(normalized_draft.get("text"), "draft.text")
        cleaned = text
        for phrase in SLOP_PHRASES:
            cleaned = cleaned.replace(phrase, "").replace(phrase.title(), "")
        cleaned = " ".join(cleaned.split())
        edited.append({**normalized_draft, "text": cleaned, "edit_notes": ["Removed predictable AI writing patterns."]})
    return {"edited_drafts": edited}


def normalize_draft_schema(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(work_order["inputs"], "drafts")
    source_format = work_order["inputs"].get("source_format", "separate_section")
    channel = _draft_channel_from_inputs(work_order["inputs"], context)
    normalized = []
    for index, draft in enumerate(drafts):
        item = _normalize_draft_shape(draft)
        if not item.get("channel"):
            item_channel = _channel_for_index(channel, index)
            if item_channel:
                item["channel"] = item_channel
        if source_format == "separate_section":
            item["text"] = _format_sources_separately(require_text(item.get("text"), "draft.text"), item.get("sources", []))
        normalized.append(item)
    return {"drafts": normalized}


def _draft_channel_from_inputs(inputs: dict[str, Any], context: dict[str, Any] | None = None) -> str | list[str] | None:
    channel = inputs.get("channel")
    if isinstance(channel, str) and channel.strip():
        return channel.strip()
    channels = inputs.get("channels")
    if isinstance(channels, list):
        normalized_channels = [str(item).strip() for item in channels if str(item).strip()]
        if normalized_channels:
            return normalized_channels
    run_input = context.get("input") if isinstance(context, dict) else None
    if isinstance(run_input, dict):
        return _draft_channel_from_inputs(run_input)
    return None


def _channel_for_index(channel: str | list[str] | None, index: int) -> str | None:
    if isinstance(channel, str):
        return channel
    if isinstance(channel, list) and channel:
        return channel[min(index, len(channel) - 1)]
    return None


def _normalize_draft_shape(draft: Any) -> dict[str, Any]:
    if isinstance(draft, dict):
        normalized = dict(draft)
    elif isinstance(draft, str) and draft.strip():
        normalized = {"text": draft.strip()}
    else:
        raise WorkerInputError("draft must be an object or non-empty string")
    if not isinstance(normalized.get("text"), str) or not normalized.get("text", "").strip():
        for text_key in ("draft_text", "body", "content", "message"):
            value = normalized.get(text_key)
            if isinstance(value, str) and value.strip():
                normalized["text"] = value.strip()
                break
    if not isinstance(normalized.get("text"), str) or not normalized.get("text", "").strip():
        thread = normalized.get("thread")
        if isinstance(thread, list) and thread:
            normalized["text"] = "\n\n".join(_thread_item_text(item) for item in thread if _thread_item_text(item))
    normalized.setdefault("status", "draft")
    normalized.setdefault("publish", False)
    text = normalized.get("text") if isinstance(normalized.get("text"), str) else ""
    sources = _draft_source_urls(normalized, text)
    claims = normalized.get("claims")
    if not isinstance(claims, list):
        thread_claims = _claims_from_thread(normalized.get("thread"))
        if thread_claims:
            claims = thread_claims
    if isinstance(claims, list):
        normalized_claims = []
        for claim in claims:
            if not isinstance(claim, dict):
                continue
            normalized_claim = _normalize_claim(claim, text)
            evidence_urls = normalized_claim.get("evidence_urls")
            if not normalized_claim.get("source_url") and isinstance(evidence_urls, list) and evidence_urls:
                normalized_claim["source_url"] = str(evidence_urls[0])
            if normalized_claim.get("source_url") and normalized_claim["source_url"] not in sources:
                sources.append(normalized_claim["source_url"])
            normalized_claims.append(normalized_claim)
        normalized["claims"] = normalized_claims
    elif sources and text.strip():
        normalized["claims"] = [{"text": text.strip(), "source_url": sources[0], "evidence_urls": sources}]
    normalized["sources"] = [str(source) for source in sources if str(source).strip()]
    return normalized


def _thread_item_text(item: Any) -> str:
    if isinstance(item, dict):
        value = item.get("text") or item.get("body") or item.get("content") or item.get("message")
        return str(value).strip() if value is not None else ""
    return str(item).strip()


def _claims_from_thread(thread: Any) -> list[dict[str, Any]]:
    if not isinstance(thread, list):
        return []
    claims: list[dict[str, Any]] = []
    for item in thread:
        if not isinstance(item, dict):
            continue
        item_text = _thread_item_text(item)
        item_claims = item.get("claims")
        if not isinstance(item_claims, list):
            continue
        for claim in item_claims:
            if not isinstance(claim, dict):
                continue
            claims.append(_normalize_claim(claim, item_text))
    return claims


def _normalize_claim(claim: dict[str, Any], fallback_text: str) -> dict[str, Any]:
    normalized_claim = dict(claim)
    if not isinstance(normalized_claim.get("text"), str) or not normalized_claim.get("text", "").strip():
        claim_text = normalized_claim.get("claim_text")
        if isinstance(claim_text, str) and claim_text.strip():
            normalized_claim["text"] = claim_text.strip()
        elif isinstance(normalized_claim.get("statement"), str) and normalized_claim["statement"].strip():
            normalized_claim["text"] = normalized_claim["statement"].strip()
        elif fallback_text.strip():
            normalized_claim["text"] = fallback_text.strip()
    return normalized_claim


def _draft_source_urls(draft: dict[str, Any], text: str) -> list[str]:
    sources: list[str] = []
    for key in ("sources", "source_urls", "evidence_urls", "evidence"):
        value = draft.get(key)
        if isinstance(value, str):
            _append_source_urls(sources, [value])
        elif isinstance(value, list):
            flattened: list[Any] = []
            for item in value:
                if isinstance(item, dict):
                    flattened.extend(
                        [
                            item.get("url"),
                            item.get("source_url"),
                            item.get("html_url"),
                            item.get("id"),
                        ]
                    )
                    evidence_urls = item.get("evidence_urls")
                    if isinstance(evidence_urls, list):
                        flattened.extend(evidence_urls)
                else:
                    flattened.append(item)
            _append_source_urls(sources, flattened)
    thread = draft.get("thread")
    if isinstance(thread, list):
        for item in thread:
            if not isinstance(item, dict):
                continue
            item_claims = item.get("claims")
            if not isinstance(item_claims, list):
                continue
            for claim in item_claims:
                if not isinstance(claim, dict):
                    continue
                _append_source_urls(sources, [claim.get("source_url")])
                evidence_urls = claim.get("evidence_urls")
                if isinstance(evidence_urls, list):
                    _append_source_urls(sources, evidence_urls)
    _append_source_urls(sources, URL_PATTERN.findall(text))
    return sources


def _append_source_urls(sources: list[str], values: list[Any]) -> None:
    for value in values:
        source = str(value or "").strip().rstrip(".,;:")
        if source.startswith(("http://", "https://")) and source not in sources:
            sources.append(source)


def _format_sources_separately(text: str, sources: list[Any]) -> str:
    clean_text = text.strip()
    clean_sources = []
    for source in sources:
        source_text = str(source).strip()
        if source_text and source_text not in clean_sources:
            clean_sources.append(source_text)
    if not clean_sources:
        return clean_text
    source_block = "\n".join(f"- {source}" for source in clean_sources)
    if "\nSources:\n" in clean_text or clean_text.endswith("\nSources:"):
        return clean_text
    return f"{clean_text}\n\nSources:\n{source_block}"


def claim_grounding(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(work_order["inputs"], "drafts")
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
            evidence_urls = claim.get("evidence_urls")
            has_source_url = isinstance(claim.get("source_url"), str) and claim["source_url"].strip()
            has_evidence_urls = isinstance(evidence_urls, list) and any(isinstance(url, str) and url.strip() for url in evidence_urls)
            if not has_source_url and not has_evidence_urls:
                checks["every_claim_has_source_url"] = False
                reasons.append("A claim is missing source_url.")
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return {"passed": all(checks.values()), "score": score, "reasons": reasons, "checks": checks}


def trend_quality(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(work_order["inputs"], "drafts")
    checks = {
        "has_drafts": bool(drafts),
        "all_have_channels": all(bool(draft.get("channel")) for draft in drafts),
        "all_have_text": all(bool(draft.get("text")) for draft in drafts),
        "no_publish_external_action": all(draft.get("publish") is not True and draft.get("status", "draft") == "draft" for draft in drafts),
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
    "draft-schema-normalizer": normalize_draft_schema,
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
    "normalize_draft_schema": normalize_draft_schema,
    "claim_grounding": claim_grounding,
    "trend_quality": trend_quality,
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
        error_payload = {
            "error_type": "WorkerInputError",
            "message": str(exc),
            "provider_failures": getattr(exc, "provider_failures", {}),
            "provider_attempts": getattr(exc, "provider_attempts", getattr(exc, "attempts", [])),
        }
        sys.stderr.write(json.dumps(error_payload, ensure_ascii=True))
        raise SystemExit(2) from None
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
