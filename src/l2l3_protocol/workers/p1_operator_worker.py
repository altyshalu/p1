from __future__ import annotations

import hashlib
import json
import os
import re
import sys
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlencode
from urllib.request import Request, urlopen

from google import genai
from google.genai import types


HTTP_TIMEOUT_SECONDS = 30
HTTP_GET_RETRY_DELAYS_SECONDS = (3, 8, 15)
USER_AGENT = "l2l3-protocol/0.1 real-p1-operator-outreach"
P1_PROVIDER_CACHE_VERSION = "p1-provider-cache-v1"
P1_PROVIDER_CACHE_TTL_SECONDS = 7 * 24 * 60 * 60
P1_DATALAKE_MIN_SCORE = 50
P1_STRONG_MIN_SCORE = 70
P1_GOLD_MIN_SCORE = 85

GOOGLE_SHEET_DEFAULT_TAB = "P1_L2L3_NEW_LEADS"
GOOGLE_SHEET_HEADERS = [
    "run_id",
    "lead_id",
    "name",
    "linkedin_url",
    "identity_status",
    "current_role",
    "gateway_decision",
    "triage_score",
    "archetype",
    "outreach_status",
    "draft_text",
    "evidence_urls",
    "claims_json",
    "runtime_source",
    "synced_at",
]
LINKEDIN_PERSON_RE = re.compile(r"^https?://(?:(?:www|[a-z]{2})\.)?linkedin\.com/in/[A-Za-z0-9%_\-]+$", re.IGNORECASE)
IDENTITY_STATUS_VERIFIED = "verified_linkedin"
IDENTITY_STATUS_REVIEW = "needs_review"

P1_REQUIRED_TRIAGE_GATES = (
    "b2c_or_plg_product_experience",
    "product_leadership",
    "verified_angel_or_check_writer",
    "geography_language_fit",
)

P1_BLOCKING_TRIAGE_GATES = (
    "excluded_industry",
    "excluded_profile_type",
)


class P1WorkerInputError(ValueError):
    pass


def require_text(value: Any, key: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise P1WorkerInputError(f"missing required non-empty string: {key}")
    return value.strip()


def require_list(value: Any, key: str) -> list[Any]:
    if not isinstance(value, list) or not value:
        raise P1WorkerInputError(f"missing required non-empty list: {key}")
    return value


def require_env(key: str) -> str:
    value = os.environ.get(key)
    if not value or not value.strip():
        raise P1WorkerInputError(f"missing required environment variable: {key}")
    return value.strip()


def read_existing_dossiers(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    inputs = work_order["inputs"]
    source_path = inputs.get("dossier_source_path") or os.environ.get("P1_DOSSIER_SOURCE_PATH")
    root = Path(require_text(source_path, "dossier_source_path"))
    if not root.exists() or not root.is_dir():
        raise P1WorkerInputError(f"dossier_source_path does not exist or is not a directory: {root}")
    limit = int(inputs.get("limit", 5))
    if limit < 1:
        raise P1WorkerInputError("limit must be >= 1")
    only_awaiting = bool(inputs.get("only_awaiting_outreach", False))
    dossiers: list[dict[str, Any]] = []
    drift_items: list[dict[str, Any]] = []
    state_counts: dict[str, int] = {}
    gateway_counts: dict[str, int] = {}
    outreach_counts: dict[str, int] = {}
    for path in sorted(root.glob("*.json")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        gateway_status = str(raw.get("gateway_evaluations", {}).get("status", ""))
        outreach_status = str(raw.get("outreach", {}).get("status", ""))
        l2_state = str(raw.get("L2_State", ""))
        state_counts[l2_state] = state_counts.get(l2_state, 0) + 1
        gateway_counts[gateway_status] = gateway_counts.get(gateway_status, 0) + 1
        outreach_counts[outreach_status] = outreach_counts.get(outreach_status, 0) + 1
        if l2_state == "OUTREACH_DRAFTED" and outreach_status == "NONE":
            drift_items.append({"file": path.name, "drift_type": "draft_state_without_draft", "l2_state": l2_state, "outreach_status": outreach_status})
        score = int(raw.get("historical_context", {}).get("v2_triage_score") or 0)
        if score < int(inputs.get("minimum_score", 50)):
            continue
        if only_awaiting and gateway_status != "Awaiting Outreach":
            continue
        if gateway_status not in {"Awaiting Outreach", "UNPROCESSED"}:
            continue
        dossiers.append(_canonical_dossier(raw, source_file=str(path)))
        if len(dossiers) >= limit:
            break
    if not dossiers:
        raise P1WorkerInputError("no eligible real dossiers found for P1 migration run")
    return {
        "p1_dossiers": dossiers,
        "drift_report": {
            "drift_count": len(drift_items),
            "items": drift_items[:50],
            "state_counts": state_counts,
            "gateway_counts": gateway_counts,
            "outreach_counts": outreach_counts,
        },
    }


def collect_sources(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    inputs = work_order["inputs"]
    sources = [str(item).strip().lower() for item in require_list(inputs.get("sources"), "sources")]
    limit = int(inputs.get("limit", 10))
    query = str(inputs.get("query") or "B2C product angel investors systematic operators").strip()
    candidates: list[dict[str, Any]] = []
    attempts: list[dict[str, Any]] = []
    for source in sources:
        started_at = time.perf_counter()
        if source == "exa":
            source_limit = min(limit, 10)
            request = {"query": query, "limit": source_limit}
            items, cache = _with_provider_cache(inputs, source, request, lambda: _exa_people_search(query, source_limit))
            attempts.append(_source_attempt_payload(source, request, len(items), cache, query=query))
            candidates.extend(items)
        elif source == "apify_funding":
            source_limit = min(limit, 10)
            request = {"inputs": _provider_cache_inputs(inputs), "limit": source_limit}
            items, cache = _with_provider_cache(inputs, source, request, lambda: _apify_funding_search(inputs, source_limit))
            attempts.append(_source_attempt_payload(source, request, len(items), cache, actor_id="nexgendata/startup-funding-tracker"))
            candidates.extend(items)
        elif source == "apify_crunchbase":
            source_limit = min(limit, 5)
            actor_id = str(inputs.get("crunchbase_actor_id") or "parseforge/crunchbase-scraper")
            request = {"inputs": _provider_cache_inputs(inputs), "limit": source_limit, "actor_id": actor_id}
            items, cache = _with_provider_cache(inputs, source, request, lambda: _apify_crunchbase_search(inputs, source_limit))
            attempts.append(_source_attempt_payload(source, request, len(items), cache, actor_id=actor_id))
            candidates.extend(items)
        elif source == "apify_linkedin":
            source_limit = min(limit, 100)
            actor_id = str(inputs.get("linkedin_actor_id") or "riceman/linkedin-sales-navigator-lead-search-scraper")
            request = {"inputs": _provider_cache_inputs(inputs), "limit": source_limit, "actor_id": actor_id}
            items, cache = _with_provider_cache(inputs, source, request, lambda: _apify_linkedin_search(inputs, source_limit))
            attempts.append(_source_attempt_payload(source, request, len(items), cache, actor_id=actor_id))
            candidates.extend(items)
        else:
            raise P1WorkerInputError(f"unsupported P1 source: {source}")
        attempts[-1]["duration_ms"] = max(0, int((time.perf_counter() - started_at) * 1000))
    primary_source = str(inputs.get("source") or (sources[0] if len(sources) == 1 else "merged"))
    return {"source": primary_source, "lead_candidates": candidates[:limit], "source_attempts": attempts}


def merge_source_batches(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    batches = require_list(work_order["inputs"].get("source_batches"), "source_batches")
    merged_candidates: list[dict[str, Any]] = []
    merged_attempts: list[dict[str, Any]] = []
    seen: set[str] = set()
    for batch in batches:
        if not isinstance(batch, dict):
            continue
        merged_attempts.extend(batch.get("source_attempts", []) if isinstance(batch.get("source_attempts"), list) else [])
        for candidate in batch.get("lead_candidates", []) if isinstance(batch.get("lead_candidates"), list) else []:
            if not isinstance(candidate, dict):
                continue
            dedupe_key = str(candidate.get("linkedin_url") or candidate.get("source_url") or candidate.get("name") or "").strip().lower()
            if not dedupe_key or dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            merged_candidates.append(candidate)
    if not merged_candidates:
        raise P1WorkerInputError("real P1 sourcing returned no lead candidates after merging source batches")
    return {"lead_candidates": merged_candidates, "source_attempts": merged_attempts, "source_batches": batches}


def normalize_leads(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    candidates = require_list(work_order["inputs"].get("lead_candidates"), "lead_candidates")
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    seen: set[str] = set()
    for candidate in candidates:
        if not isinstance(candidate, dict):
            rejected.append({"reason": "candidate_not_object", "candidate": candidate})
            continue
        name = str(candidate.get("name") or "").strip()
        if not name or _looks_like_company(name):
            rejected.append({"reason": "not_a_single_human", "candidate": candidate})
            continue
        if not _has_clean_person_name(name):
            rejected.append({"reason": "invalid_person_name", "candidate": candidate})
            continue
        url = _clean_url(str(candidate.get("linkedin_url") or candidate.get("source_url") or ""))
        if url and 'linkedin.com/company/' in url:
            rejected.append({"reason": "no_person_linkedin", "candidate": candidate})
            continue
        person_url = url if LINKEDIN_PERSON_RE.match(url) else ""
        dedupe_key = (person_url or name).lower()
        if dedupe_key in seen:
            rejected.append({"reason": "duplicate", "candidate": candidate})
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "lead_id": _deterministic_lead_id(name, person_url, _clean_url(str(candidate.get("source_url") or url))),
                "name": name,
                "headline": str(candidate.get("headline") or "Angel investor / operator").strip(),
                "linkedin_url": person_url,
                "source_url": _clean_url(str(candidate.get("source_url") or url)),
                "source": str(candidate.get("source") or "unknown"),
                "identity_status": IDENTITY_STATUS_VERIFIED if person_url else IDENTITY_STATUS_REVIEW,
                "evidence": candidate.get("evidence") if isinstance(candidate.get("evidence"), list) else [],
            }
        )
    if not normalized:
        raise P1WorkerInputError(f"all P1 lead candidates were rejected: {rejected[:5]}")
    return {"normalized_leads": normalized, "rejected_leads": rejected}


def score_triage(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    client = _gemini_client()
    leads = require_list(work_order["inputs"].get("normalized_leads"), "normalized_leads")
    scores = []
    for lead in leads:
        response = _gemini_json(
            client,
            f"""
You are the P1 Triage Agent for Limpid/ABRT.
Score this real operator/angel lead.

Lead:
{json.dumps(lead, ensure_ascii=False)}

Rules:
- Use the canonical P1 Golden ICP: B2C/PLG product leader AND verified angel/check-writer.
- b2c_plg_dna_score: 0-30 for consumer, PLG, mobile, social, gaming, marketplace, fintech, viral, product-led, user-scale DNA.
- product_leadership_score: 0-20 for CPO, VP Product, Head of Product, Lead PM, product-owning founder, growth/product owner.
- verified_angel_score: 0-25 for explicit personal angel investing, syndicate, portfolio, AngelList, Crunchbase, Dealroom, PitchBook, NfX Signal, or micro-fund proof.
- liquidity_ecosystem_score: 0-10 for unicorn/major exit/elite product ecosystem.
- systematic_fit_score: 0-10 for data-driven, AI, ML, quant, systematic, framework, evidence, metrics, analytics.
- geography_language_score: 0-5 for priority hub and English-language fit.
- hard_gates.b2c_or_plg_product_experience true only when real product-led B2C/PLG evidence exists.
- hard_gates.product_leadership true only when real product ownership exists.
- hard_gates.verified_angel_or_check_writer true only when personal investing/check-writing evidence exists, not advisor/mentor/VC title alone.
- hard_gates.geography_language_fit false for India, LATAM, or non-English profiles under current P1 policy.
- hard_gates.excluded_industry true for enterprise-only B2B SaaS, defense/military, biotech, heavy industry, legal, corporate finance, academic-only, consulting-only.
- hard_gates.excluded_profile_type true for mentor-only, advisor-only, investor relations, corporate VC only, traditional VC partner without personal portfolio, or investor-only without operator history.
- evidence_urls must include the source URLs supporting the score when available.
Return JSON only with keys: b2c_plg_dna_score, product_leadership_score, verified_angel_score, liquidity_ecosystem_score, systematic_fit_score, geography_language_score, hard_gates, evidence_urls, reasoning.
""",
        )
        triage = _normalize_triage_result(response)
        scores.append({**lead, "triage": triage})
    return {"triage_scores": scores}


def _normalize_triage_result(response: dict[str, Any]) -> dict[str, Any]:
    b2c_score = _bounded_int(response.get("b2c_plg_dna_score", response.get("b2c_dna_score")), 0, 30)
    product_score = _bounded_int(response.get("product_leadership_score"), 0, 20)
    angel_score = _bounded_int(response.get("verified_angel_score", response.get("investor_score")), 0, 25)
    liquidity_score = _bounded_int(response.get("liquidity_ecosystem_score"), 0, 10)
    systematic_score = _bounded_int(response.get("systematic_fit_score", response.get("systematic_score")), 0, 10)
    geography_score = _bounded_int(response.get("geography_language_score"), 0, 5)
    hard_gates = response.get("hard_gates") if isinstance(response.get("hard_gates"), dict) else {}
    normalized_gates = {
        "b2c_or_plg_product_experience": _bool_gate(hard_gates.get("b2c_or_plg_product_experience")),
        "product_leadership": _bool_gate(hard_gates.get("product_leadership")),
        "verified_angel_or_check_writer": _bool_gate(hard_gates.get("verified_angel_or_check_writer")),
        "geography_language_fit": _bool_gate(hard_gates.get("geography_language_fit")),
        "excluded_industry": _bool_gate(hard_gates.get("excluded_industry") or response.get("is_blacklist")),
        "excluded_profile_type": _bool_gate(hard_gates.get("excluded_profile_type")),
    }
    total = b2c_score + product_score + angel_score + liquidity_score + systematic_score + geography_score
    missing_required = [gate for gate in P1_REQUIRED_TRIAGE_GATES if normalized_gates.get(gate) is not True]
    blocking_gates = [gate for gate in P1_BLOCKING_TRIAGE_GATES if normalized_gates.get(gate) is True]
    status = _triage_status(total, missing_required, blocking_gates)
    evidence_urls = response.get("evidence_urls") if isinstance(response.get("evidence_urls"), list) else []
    return {
        **response,
        "b2c_plg_dna_score": b2c_score,
        "product_leadership_score": product_score,
        "verified_angel_score": angel_score,
        "liquidity_ecosystem_score": liquidity_score,
        "systematic_fit_score": systematic_score,
        "geography_language_score": geography_score,
        "hard_gates": normalized_gates,
        "evidence_urls": [_clean_url(str(url)) for url in evidence_urls if _clean_url(str(url))],
        "total_score": total,
        "quality_band": _quality_band(total),
        "missing_required_gates": missing_required,
        "blocking_gates": blocking_gates,
        "qualified": status == "gateway_eligible",
        "datalake_eligible": status in {"gateway_eligible", "data_lake_only"},
        "status": status,
        "reject_reason": _triage_reject_reason(total, missing_required, blocking_gates, status),
    }


def _bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))


def _bool_gate(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "passed"}
    return False


def _quality_band(total: int) -> str:
    if total >= P1_GOLD_MIN_SCORE:
        return "gold"
    if total >= P1_STRONG_MIN_SCORE:
        return "strong"
    if total >= P1_DATALAKE_MIN_SCORE:
        return "data_lake_only"
    return "reject"


def _triage_status(total: int, missing_required: list[str], blocking_gates: list[str]) -> str:
    if blocking_gates:
        return "reject"
    if missing_required:
        return "needs_enrichment" if total >= P1_STRONG_MIN_SCORE else "reject"
    if total >= P1_STRONG_MIN_SCORE:
        return "gateway_eligible"
    if total >= P1_DATALAKE_MIN_SCORE:
        return "data_lake_only"
    return "reject"


def _triage_reject_reason(total: int, missing_required: list[str], blocking_gates: list[str], status: str) -> str:
    if status == "gateway_eligible":
        return ""
    if blocking_gates:
        return f"blocking_gates:{','.join(blocking_gates)}"
    if missing_required:
        return f"missing_required_gates:{','.join(missing_required)}"
    if status == "data_lake_only":
        return f"score_below_gateway_threshold:{total}"
    return f"score_below_datalake_threshold:{total}"


def write_dossiers(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    scores = require_list(work_order["inputs"].get("triage_scores"), "triage_scores")
    dossiers = []
    rejected = []
    for item in scores:
        triage = item.get("triage") if isinstance(item.get("triage"), dict) else {}
        if not triage.get("qualified"):
            rejected.append(
                {
                    "name": item.get("name"),
                    "reason": triage.get("reject_reason") or "triage_not_gateway_eligible",
                    "score": triage.get("total_score"),
                    "quality_band": triage.get("quality_band"),
                    "status": triage.get("status"),
                    "missing_required_gates": triage.get("missing_required_gates", []),
                    "blocking_gates": triage.get("blocking_gates", []),
                }
            )
            continue
        dossiers.append(
            {
                "identity": {
                    "name": item["name"],
                    "lead_id": item.get("lead_id"),
                    "linkedin_url": item.get("linkedin_url", ""),
                    "alternative_urls": [item.get("source_url")] if item.get("source_url") and item.get("source_url") != item.get("linkedin_url") else [],
                    "identity_status": item.get("identity_status"),
                },
                "historical_context": {
                    "sources_found": [item.get("source", "runtime_source")],
                    "all_recorded_headlines": [item.get("headline", "")],
                    "raw_notes_and_reasoning": [triage.get("reasoning", "")],
                    "v2_triage_score": triage.get("total_score"),
                    "v2_triage_reasoning": triage.get("reasoning", ""),
                    "p1_quality_band": triage.get("quality_band"),
                    "p1_hard_gates": triage.get("hard_gates", {}),
                    "p1_triage_status": triage.get("status"),
                    "p1_evidence_urls": triage.get("evidence_urls", []),
                },
                "live_intelligence": {"last_updated": None, "exa_raw_urls": [], "exa_snippets": []},
                "gateway_evaluations": {"status": "UNPROCESSED"},
                "outreach": {"status": "NONE", "draft_message": ""},
                "runtime_source": "p1-operator-outreach",
            }
        )
    if not dossiers:
        raise P1WorkerInputError(f"no qualified dossiers after triage: {rejected[:5]}")
    return {"p1_dossiers": dossiers, "rejected_after_triage": rejected}


def gather_live_intelligence(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    dossiers = require_list(work_order["inputs"].get("p1_dossiers"), "p1_dossiers")
    updated = []
    for dossier in dossiers:
        canonical = _canonical_dossier(dossier)
        name = canonical["identity"]["name"]
        headline = canonical["historical_context"]["all_recorded_headlines"][0] if canonical["historical_context"]["all_recorded_headlines"] else "operator investor"
        query = f"{name} {headline} current role angel investor operator product LinkedIn"
        results = _exa_people_search(query, int(work_order["inputs"].get("exa_results_per_dossier", 5)))
        if not results:
            raise P1WorkerInputError(f"Exa returned no live intelligence for dossier: {name}")
        canonical["live_intelligence"] = {
            "last_updated": time.strftime("%Y-%m-%d %H:%M:%S"),
            "exa_raw_urls": [item["source_url"] for item in results if item.get("source_url")],
            "exa_snippets": [
                {"url": item.get("source_url", ""), "title": item.get("headline", ""), "snippet": " ".join(item.get("evidence", []))[:800]}
                for item in results
            ],
        }
        live_linkedin_url = _linkedin_person_url_from_urls(canonical["live_intelligence"]["exa_raw_urls"])
        if live_linkedin_url and not canonical["identity"].get("linkedin_url"):
            canonical["identity"]["linkedin_url"] = live_linkedin_url
            canonical["identity"]["identity_status"] = IDENTITY_STATUS_VERIFIED
        updated.append(canonical)
    return {"p1_dossiers": updated}


def evaluate_gateway(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    client = _gemini_client()
    dossiers = require_list(work_order["inputs"].get("p1_dossiers"), "p1_dossiers")
    verify_linkedin_live = bool(work_order["inputs"].get("verify_linkedin_live", False))
    evaluations = []
    for dossier in dossiers:
        response = _gemini_json(
            client,
            f"""
You are the P1 Trifecta Gateway evaluator for Limpid/ABRT.
Evaluate whether this real operator/angel dossier can enter outreach.

Dossier:
{json.dumps(dossier, ensure_ascii=False)[:12000]}

Rules:
- identity_confidence 0-100.
- product_b2c_fit PASS only when the dossier has B2C/PLG product-building evidence.
- product_leadership_fit PASS only when the person owned product as CPO, VP Product, Head of Product, Lead PM, or product-owning founder/operator.
- verified_investor_fit PASS only when there is personal angel/check-writing, syndicate, portfolio, AngelList, Crunchbase, Dealroom, PitchBook, NfX Signal, or micro-fund proof.
- bandwidth_signal HIGH only for advisors, angel investors, solo/fractional/stealth builders, independent operators, or not currently overloaded.
- bandwidth_signal LOW for active C-suite/VP/Director/Partner/GP at substantial operating company.
- liquidity_signal YES when unicorn/major exit/known high-growth operator/investor evidence exists.
- systematic_alignment YES when data/AI/product/scaling/systematic evidence exists.
- exclusion_signal YES when the profile is enterprise-only, corporate finance, defense/military, biotech, heavy industry, legal, academic-only, consulting-only, India, LATAM, non-English, mentor-only, advisor-only, corporate VC-only, or traditional VC-only without personal portfolio.
- evidence_urls must include the URLs used to support the decision.
Return JSON only with keys: identity_confidence, product_b2c_fit, product_leadership_fit, verified_investor_fit, bandwidth_signal, liquidity_signal, systematic_alignment, exclusion_signal, current_role_verified, evidence_urls, mythos_dossier.
""",
        )
        gateway = _normalize_gateway_result(response)
        _apply_identity_quality_gate(dossier, gateway, verify_linkedin_live=verify_linkedin_live)
        evaluations.append({"dossier": dossier, "gateway": gateway})
    return {"gateway_evaluations": evaluations}


def _normalize_gateway_result(response: dict[str, Any]) -> dict[str, Any]:
    confidence = _bounded_int(response.get("identity_confidence"), 0, 100)
    bandwidth = str(response.get("bandwidth_signal", "UNKNOWN")).strip().upper()
    liquidity = str(response.get("liquidity_signal", "UNKNOWN")).strip().upper()
    product_b2c = _pass_signal(response.get("product_b2c_fit"))
    product_leadership = _pass_signal(response.get("product_leadership_fit"))
    verified_investor = _pass_signal(response.get("verified_investor_fit"))
    systematic = str(response.get("systematic_alignment", "UNKNOWN")).strip().upper()
    exclusion = str(response.get("exclusion_signal", "UNKNOWN")).strip().upper()
    evidence_urls = response.get("evidence_urls") if isinstance(response.get("evidence_urls"), list) else []
    decision, reasons = _gateway_decision(
        confidence=confidence,
        product_b2c=product_b2c,
        product_leadership=product_leadership,
        verified_investor=verified_investor,
        bandwidth=bandwidth,
        liquidity=liquidity,
        exclusion=exclusion,
        evidence_urls=evidence_urls,
    )
    return {
        **response,
        "identity_confidence": confidence,
        "product_b2c_fit": "PASS" if product_b2c else "FAIL",
        "product_leadership_fit": "PASS" if product_leadership else "FAIL",
        "verified_investor_fit": "PASS" if verified_investor else "FAIL",
        "bandwidth_signal": bandwidth,
        "liquidity_signal": liquidity,
        "systematic_alignment": systematic,
        "exclusion_signal": exclusion,
        "evidence_urls": [_clean_url(str(url)) for url in evidence_urls if _clean_url(str(url))],
        "decision": decision,
        "decision_reasons": reasons,
    }


def _pass_signal(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().upper() in {"PASS", "YES", "TRUE", "1"}
    return False


def _gateway_decision(
    *,
    confidence: int,
    product_b2c: bool,
    product_leadership: bool,
    verified_investor: bool,
    bandwidth: str,
    liquidity: str,
    exclusion: str,
    evidence_urls: list[Any],
) -> tuple[str, list[str]]:
    reasons: list[str] = []
    if confidence < 90:
        return "identity_mismatch", [f"identity_confidence_below_90:{confidence}"]
    if exclusion == "YES":
        reasons.append("exclusion_signal")
    if not product_b2c:
        reasons.append("missing_b2c_plg_product_fit")
    if not product_leadership:
        reasons.append("missing_product_leadership_fit")
    if not verified_investor:
        reasons.append("missing_verified_angel_or_check_writer_fit")
    if bandwidth != "HIGH":
        reasons.append(f"bandwidth_not_high:{bandwidth}")
    if liquidity != "YES":
        reasons.append(f"liquidity_not_yes:{liquidity}")
    if not evidence_urls:
        reasons.append("missing_gateway_evidence_urls")
    if not reasons:
        return "awaiting_outreach", []
    if any(reason.startswith("bandwidth_not_high") or reason.startswith("liquidity_not_yes") or reason == "exclusion_signal" for reason in reasons):
        return "bypass", reasons
    return "needs_more_evidence", reasons


def _apply_identity_quality_gate(dossier: dict[str, Any], gateway: dict[str, Any], verify_linkedin_live: bool = False) -> None:
    identity = dossier.get("identity") if isinstance(dossier.get("identity"), dict) else {}
    linkedin_url = _clean_url(str(identity.get("linkedin_url") or ""))
    identity_status = str(identity.get("identity_status") or "").strip()
    reasons = gateway.get("decision_reasons")
    if not isinstance(reasons, list):
        reasons = []
    if not LINKEDIN_PERSON_RE.match(linkedin_url):
        reasons.append("missing_verified_person_linkedin")
    if identity_status != IDENTITY_STATUS_VERIFIED:
        reasons.append(f"identity_status_not_verified:{identity_status or IDENTITY_STATUS_REVIEW}")
    if verify_linkedin_live and LINKEDIN_PERSON_RE.match(linkedin_url) and not _linkedin_profile_url_is_live(linkedin_url):
        reasons.append("linkedin_profile_not_live")
    deduped_reasons = list(dict.fromkeys(str(reason) for reason in reasons if str(reason).strip()))
    if deduped_reasons:
        gateway["decision_reasons"] = deduped_reasons
        if gateway.get("decision") == "awaiting_outreach":
            gateway["decision"] = "needs_more_evidence"


def build_forge_queue(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    evaluations = require_list(work_order["inputs"].get("gateway_evaluations"), "gateway_evaluations")
    queue = [item for item in evaluations if item.get("gateway", {}).get("decision") == "awaiting_outreach"]
    bypassed = [item for item in evaluations if item.get("gateway", {}).get("decision") != "awaiting_outreach"]
    if not queue:
        raise P1WorkerInputError(f"no gateway-approved operators for outreach; bypassed={len(bypassed)}")
    return {"forge_queue": queue, "bypassed": bypassed}


def write_outreach_drafts(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    client = _gemini_client()
    queue = require_list(work_order["inputs"].get("forge_queue"), "forge_queue")
    drafts = []
    for item in queue:
        dossier = item["dossier"]
        gateway = item["gateway"]
        response = _gemini_json(
            client,
            f"""
Write a short peer-to-peer outreach draft for this real P1 operator.

Dossier:
{json.dumps(dossier, ensure_ascii=False)[:9000]}

Gateway:
{json.dumps(gateway, ensure_ascii=False)}

Constraints:
- Max 90 words excluding greeting.
- No transactional offer.
- Mention ABRT or Limpid as an AI-native/operator-led VC model.
- Use only evidence from dossier/gateway/live intelligence.
- Ask whether the thesis resonates and propose a 30-minute call next week.
- Return JSON only with keys: archetype, draft, evidence_urls, claims.
- archetype must be Builder or Collector.
- claims must be an array of objects with text and source_url.
""",
        )
        evidence_urls = response.get("evidence_urls")
        if not isinstance(evidence_urls, list) or not evidence_urls:
            evidence_urls = dossier.get("live_intelligence", {}).get("exa_raw_urls", [])[:3]
        lead_id = dossier.get("identity", {}).get("lead_id") or _deterministic_lead_id(dossier["identity"]["name"], dossier["identity"].get("linkedin_url", ""), evidence_urls[0] if evidence_urls else "")
        run_id = str(work_order.get("run_id") or "")
        draft = {
            "run_id": run_id,
            "lead_id": lead_id,
            "idempotency_key": _draft_idempotency_key(run_id, lead_id),
            "runtime_source": "p1-operator-outreach",
            "name": dossier["identity"]["name"],
            "linkedin_url": dossier["identity"].get("linkedin_url", ""),
            "identity_status": dossier["identity"].get("identity_status", IDENTITY_STATUS_REVIEW),
            "current_role": _normalize_current_role(gateway.get("current_role_verified", "")),
            "gateway_decision": gateway.get("decision", "awaiting_outreach"),
            "triage_score": dossier.get("historical_context", {}).get("v2_triage_score"),
            "archetype": response.get("archetype"),
            "text": _normalize_outreach_text(require_text(response.get("draft"), "draft")),
            "evidence_urls": evidence_urls,
            "claims": _normalize_claims(response.get("claims"), evidence_urls),
            "status": "draft",
            "publish": False,
        }
        drafts.append(draft)
    return {"outreach_drafts": drafts}


def judge_outreach_quality(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(work_order["inputs"].get("outreach_drafts"), "outreach_drafts")
    verify_linkedin_live = bool(work_order["inputs"].get("verify_linkedin_live", False))
    reasons: list[str] = []
    checks = {
        "has_drafts": bool(drafts),
        "all_have_text": all(isinstance(item.get("text"), str) and item["text"].strip() for item in drafts),
        "all_have_evidence_urls": all(isinstance(item.get("evidence_urls"), list) and item["evidence_urls"] for item in drafts),
        "all_claims_have_sources": all(_claims_have_sources(item) for item in drafts),
        "no_publish_external_action": all(item.get("publish") is not True and item.get("status") == "draft" for item in drafts),
        "word_count_under_110": all(len(str(item.get("text", "")).split()) <= 110 for item in drafts),
        "mentions_abrt_or_limpid": all(("abrt" in str(item.get("text", "")).lower()) or ("limpid" in str(item.get("text", "")).lower()) for item in drafts),
        "has_clear_cta": all(_has_clear_cta(str(item.get("text", ""))) for item in drafts),
        "single_meeting_cta": all(_meeting_cta_count(str(item.get("text", ""))) <= 1 for item in drafts),
        "no_placeholder_signoff": all(not _has_placeholder_signoff(str(item.get("text", ""))) for item in drafts),
        "all_have_idempotency_key": all(str(item.get("idempotency_key") or "").strip() for item in drafts),
        "all_have_verified_person_linkedin": all(_draft_has_verified_person_linkedin(item) for item in drafts),
        "all_linkedin_urls_are_evidence_backed": all(_draft_linkedin_has_evidence(item) for item in drafts),
    }
    if verify_linkedin_live:
        checks["all_have_live_linkedin_profile"] = all(_draft_has_live_linkedin_profile(item) for item in drafts)
    for key, passed in checks.items():
        if not passed:
            reasons.append(key)
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return {"passed": all(checks.values()), "score": score, "reasons": reasons, "checks": checks, "approval_package": {"outreach_drafts": drafts, "approval_required": True, "idempotency_keys": [item.get("idempotency_key") for item in drafts], "rows": len(drafts)}}


def sync_google_sheets(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not bool(work_order["inputs"].get("allow_google_sheet_write", False)):
        raise P1WorkerInputError("Google Sheets sync requested without allow_google_sheet_write=true")
    spreadsheet_id = str(work_order["inputs"].get("spreadsheet_id") or os.environ.get("P1_GOOGLE_SHEET_ID") or "").strip()
    if not spreadsheet_id:
        raise P1WorkerInputError("missing required spreadsheet_id or P1_GOOGLE_SHEET_ID")
    tab_name = str(work_order["inputs"].get("google_sheet_tab") or GOOGLE_SHEET_DEFAULT_TAB).strip()
    if not tab_name:
        raise P1WorkerInputError("google_sheet_tab must be a non-empty string")
    service_account_path = str(work_order["inputs"].get("google_service_account_path") or os.environ.get("GOOGLE_SA_PATH") or "").strip()
    if not service_account_path:
        raise P1WorkerInputError("missing required google_service_account_path or GOOGLE_SA_PATH")
    drafts = require_list(work_order["inputs"].get("approval_package", {}).get("outreach_drafts") or work_order["inputs"].get("outreach_drafts"), "outreach_drafts")
    token = _google_access_token(service_account_path)
    created_tab = _ensure_google_sheet_tab(spreadsheet_id, tab_name, token)
    _ensure_google_sheet_headers(spreadsheet_id, tab_name, token)
    existing_rows = _read_google_sheet_values(spreadsheet_id, f"{tab_name}!A:O", token)
    header = existing_rows[0] if existing_rows else GOOGLE_SHEET_HEADERS
    run_idx = header.index("run_id") if "run_id" in header else 0
    lead_idx = header.index("lead_id") if "lead_id" in header else 1
    existing_pairs = {
        (str(row[run_idx]).strip(), str(row[lead_idx]).strip())
        for row in existing_rows[1:]
        if len(row) > max(run_idx, lead_idx)
    }
    values = []
    skipped = 0
    synced_at = time.strftime("%Y-%m-%d %H:%M:%S")
    for draft in drafts:
        run_id = str(draft.get("run_id") or work_order.get("run_id") or "").strip()
        lead_id = str(draft.get("lead_id") or "").strip()
        if not run_id or not lead_id:
            raise P1WorkerInputError("every outreach draft must include run_id and lead_id for idempotent sheet sync")
        pair = (run_id, lead_id)
        if pair in existing_pairs:
            skipped += 1
            continue
        values.append([
            run_id,
            lead_id,
            draft.get("name", ""),
            draft.get("linkedin_url", ""),
            draft.get("identity_status", IDENTITY_STATUS_REVIEW),
            draft.get("current_role", "unknown"),
            draft.get("gateway_decision", "awaiting_outreach"),
            draft.get("triage_score", ""),
            draft.get("archetype", ""),
            draft.get("status", "draft"),
            draft.get("text", ""),
            "\n".join(str(url) for url in draft.get("evidence_urls", [])),
            json.dumps(draft.get("claims", []), ensure_ascii=False),
            draft.get("runtime_source", "p1-operator-outreach"),
            synced_at,
        ])
        existing_pairs.add(pair)
    updated_range = None
    if values:
        payload = _request_json(
            f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{quote(f'{tab_name}!A:O', safe='')}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
            method="POST",
            token=token,
            body={"values": values},
        )
        updated_range = payload.get("updates", {}).get("updatedRange")
    return {
        "sync_result": {
            "spreadsheet_id": spreadsheet_id,
            "tab_name": tab_name,
            "updated_range": updated_range,
            "row_count": len(values),
            "skipped_duplicate_count": skipped,
            "created_tab": created_tab,
        },
        "external_actions": [{"type": "google_sheets_append", "spreadsheet_id": spreadsheet_id, "tab_name": tab_name, "row_count": len(values)}],
    }


def sync_data_lake(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not bool(work_order["inputs"].get("allow_data_lake_write", False)):
        raise P1WorkerInputError("Data Lake sync requested without allow_data_lake_write=true")
    output_path = (
        work_order["inputs"].get("data_lake_dossier_path")
        or work_order["inputs"].get("dossier_output_path")
        or os.environ.get("P1_DOSSIER_OUTPUT_PATH")
    )
    root = Path(require_text(output_path, "data_lake_dossier_path"))
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise P1WorkerInputError(f"data_lake_dossier_path is not a directory: {root}")
    dossiers = require_list(work_order["inputs"].get("p1_dossiers"), "p1_dossiers")
    written = []
    skipped = 0
    updated = 0
    for dossier in dossiers:
        canonical = _canonical_dossier({**dossier, "runtime_source": "p1-operator-outreach"})
        payload = {**canonical, "runtime_source": "p1-operator-outreach", "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        identity = payload["identity"]
        lead_id = str(identity.get("lead_id") or _deterministic_lead_id(identity["name"], identity.get("linkedin_url", ""), ""))
        path = root / f"{lead_id}.json"
        body = json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
        if path.exists():
            existing = path.read_text(encoding="utf-8")
            if existing == body:
                skipped += 1
                written.append({"name": identity["name"], "path": str(path), "status": "skipped"})
                continue
            updated += 1
        path.write_text(body, encoding="utf-8")
        written.append({"name": identity["name"], "lead_id": lead_id, "path": str(path), "status": "written"})
    return {
        "sync_result": {"target_path": str(root), "written_count": len([item for item in written if item["status"] == "written"]), "updated_count": updated, "skipped_duplicate_count": skipped, "files": written},
        "external_actions": [{"type": "data_lake_json_write", "target_path": str(root), "written_count": len(written)}],
    }


def sync_outreach_master(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not bool(work_order["inputs"].get("allow_outreach_master_write", False)):
        raise P1WorkerInputError("Outreach Master sync requested without allow_outreach_master_write=true")
    master_path = Path(require_text(work_order["inputs"].get("outreach_master_path") or os.environ.get("P1_OUTREACH_MASTER_PATH"), "outreach_master_path"))
    master_path.parent.mkdir(parents=True, exist_ok=True)
    existing: dict[str, Any]
    if master_path.exists():
        loaded = json.loads(master_path.read_text(encoding="utf-8"))
        if isinstance(loaded, list):
            existing = {"drafts": loaded}
        elif isinstance(loaded, dict):
            existing = loaded
        else:
            raise P1WorkerInputError(f"Outreach Master JSON must be an object or array: {master_path}")
    else:
        existing = {"drafts": []}
    drafts = require_list(
        work_order["inputs"].get("approval_package", {}).get("outreach_drafts") or work_order["inputs"].get("outreach_drafts"),
        "outreach_drafts",
    )
    existing_drafts = existing.get("drafts")
    if not isinstance(existing_drafts, list):
        raise P1WorkerInputError("Outreach Master JSON object must contain a drafts array")
    existing_pairs = {(str(item.get("run_id") or ""), str(item.get("lead_id") or "")) for item in existing_drafts if isinstance(item, dict)}
    additions = []
    skipped = 0
    for draft in drafts:
        if not isinstance(draft, dict):
            raise P1WorkerInputError("outreach_drafts must contain objects")
        pair = (str(draft.get("run_id") or ""), str(draft.get("lead_id") or ""))
        if not pair[0] or not pair[1]:
            raise P1WorkerInputError("Outreach Master sync requires run_id and lead_id on each draft")
        if pair in existing_pairs:
            skipped += 1
            continue
        item = {
            **draft,
            "runtime_source": "p1-operator-outreach",
            "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": draft.get("status") or "draft",
            "publish": False,
        }
        additions.append(item)
        existing_pairs.add(pair)
    existing["drafts"] = [*existing_drafts, *additions]
    master_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "sync_result": {"path": str(master_path), "written_count": len(additions), "total_drafts": len(existing["drafts"]), "skipped_duplicate_count": skipped},
        "external_actions": [{"type": "outreach_master_json_append", "path": str(master_path), "written_count": len(additions)}],
    }


def build_metrics_report(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    inputs = work_order["inputs"]
    source_batches = inputs.get("source_batches", [])
    lead_candidates = inputs.get("lead_candidates", [])
    normalized_leads = inputs.get("normalized_leads", [])
    rejected_leads = inputs.get("rejected_leads", [])
    triage_scores = inputs.get("triage_scores", [])
    dossiers = inputs.get("p1_dossiers", [])
    gateway_evaluations = inputs.get("gateway_evaluations", [])
    outreach_drafts = inputs.get("outreach_drafts", [])
    quality_eval = inputs.get("quality_eval", {})
    sync_results = inputs.get("external_sync_results", {})
    task_timings = inputs.get("task_timings", [])
    if not isinstance(sync_results, dict):
        sync_results = {}
    triage_qualified = [
        item for item in triage_scores
        if isinstance(item, dict) and isinstance(item.get("triage"), dict) and item["triage"].get("qualified") is True
    ]
    triage_rejected = [
        item for item in triage_scores
        if isinstance(item, dict) and isinstance(item.get("triage"), dict) and item["triage"].get("qualified") is not True
    ]
    gateway_approved = [
        item for item in gateway_evaluations
        if isinstance(item, dict) and isinstance(item.get("gateway"), dict) and item["gateway"].get("decision") == "awaiting_outreach"
    ]
    gateway_rejected = [
        item for item in gateway_evaluations
        if isinstance(item, dict) and isinstance(item.get("gateway"), dict) and item["gateway"].get("decision") != "awaiting_outreach"
    ]
    rejection_buckets: dict[str, int] = {}
    for item in rejected_leads if isinstance(rejected_leads, list) else []:
        if isinstance(item, dict):
            reason = str(item.get("reason") or "unknown")
            rejection_buckets[reason] = rejection_buckets.get(reason, 0) + 1
    source_counts: dict[str, int] = {}
    cache_hits = 0
    for batch in source_batches if isinstance(source_batches, list) else []:
        if not isinstance(batch, dict):
            continue
        source = str(batch.get("source") or "unknown")
        source_counts[source] = len(batch.get("lead_candidates", []) if isinstance(batch.get("lead_candidates"), list) else [])
        for attempt in batch.get("source_attempts", []) if isinstance(batch.get("source_attempts"), list) else []:
            if isinstance(attempt, dict) and attempt.get("cache_hit") is True:
                cache_hits += 1
    duration_by_worker: dict[str, int] = {}
    for item in task_timings if isinstance(task_timings, list) else []:
        if not isinstance(item, dict):
            continue
        worker = str(item.get("worker_profile") or item.get("task_type") or "unknown")
        duration_by_worker[worker] = duration_by_worker.get(worker, 0) + int(item.get("duration_ms") or 0)
    source_duration_ms = sum(duration_by_worker.get(worker, 0) for worker in ("p1-source-collector", "p1-source-merger", "p1-lead-normalizer"))
    triage_duration_ms = sum(duration_by_worker.get(worker, 0) for worker in ("p1-triage-scorer", "p1-dossier-writer"))
    gateway_duration_ms = sum(duration_by_worker.get(worker, 0) for worker in ("p1-live-intel-gatherer", "p1-gateway-evaluator", "p1-forge-queue-builder"))
    drafting_duration_ms = sum(duration_by_worker.get(worker, 0) for worker in ("p1-outreach-draft-writer", "p1-outreach-quality-judge"))
    sync_duration_ms = sum(duration_by_worker.get(worker, 0) for worker in ("p1-data-lake-syncer", "p1-google-sheets-syncer", "p1-outreach-master-syncer"))
    metrics = {
        "raw_leads": len(lead_candidates) if isinstance(lead_candidates, list) else 0,
        "normalized_leads": len(normalized_leads) if isinstance(normalized_leads, list) else 0,
        "rejected_leads": len(rejected_leads) if isinstance(rejected_leads, list) else 0,
        "triage_qualified": len(triage_qualified),
        "triage_rejected": len(triage_rejected),
        "dossiers": len(dossiers) if isinstance(dossiers, list) else 0,
        "gateway_approved": len(gateway_approved),
        "gateway_rejected": len(gateway_rejected),
        "drafted": len(outreach_drafts) if isinstance(outreach_drafts, list) else 0,
        "eval_passed": bool(quality_eval.get("passed")) if isinstance(quality_eval, dict) else False,
        "sheet_written": int((sync_results.get("google_sheets") or {}).get("row_count") or 0),
        "sheet_duplicate_skipped": int((sync_results.get("google_sheets") or {}).get("skipped_duplicate_count") or 0),
        "data_lake_written": int((sync_results.get("data_lake") or {}).get("written_count") or 0),
        "data_lake_duplicate_skipped": int((sync_results.get("data_lake") or {}).get("skipped_duplicate_count") or 0),
        "outreach_master_written": int((sync_results.get("outreach_master") or {}).get("written_count") or 0),
        "outreach_master_duplicate_skipped": int((sync_results.get("outreach_master") or {}).get("skipped_duplicate_count") or 0),
        "rejection_buckets": rejection_buckets,
        "source_counts": source_counts,
        "source_quality_by_source": _source_quality_by_source(source_batches, normalized_leads, triage_scores, gateway_evaluations),
        "provider_cache_hits": cache_hits,
        "duration_by_worker_ms": duration_by_worker,
        "total_duration_ms": sum(duration_by_worker.values()),
        "source_duration_ms": source_duration_ms,
        "triage_duration_ms": triage_duration_ms,
        "gateway_duration_ms": gateway_duration_ms,
        "drafting_duration_ms": drafting_duration_ms,
        "sync_duration_ms": sync_duration_ms,
    }
    return {"metrics": metrics, "summary": _metrics_summary(metrics)}



def _deterministic_lead_id(name: str, linkedin_url: str, source_url: str) -> str:
    raw = "|".join(part.strip().lower() for part in [name, linkedin_url, source_url] if part)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


def _draft_idempotency_key(run_id: str, lead_id: str) -> str:
    return f"{run_id}:{lead_id}"


def _normalize_current_role(value: Any) -> str:
    text = str(value or "").strip().lower()
    if not text:
        return "unknown"
    if text in {"true", "yes", "current", "verified"}:
        return "yes"
    if text in {"false", "no", "former"}:
        return "no"
    return text


def _ensure_google_sheet_tab(spreadsheet_id: str, tab_name: str, token: str) -> bool:
    metadata = _request_json(f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?fields=sheets.properties", token=token)
    sheets = metadata.get("sheets", []) if isinstance(metadata, dict) else []
    existing = {str(item.get("properties", {}).get("title") or "") for item in sheets if isinstance(item, dict)}
    if tab_name in existing:
        return False
    _request_json(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
        method="POST",
        token=token,
        body={"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    )
    return True


def _read_google_sheet_values(spreadsheet_id: str, range_name: str, token: str) -> list[list[str]]:
    payload = _request_json(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{quote(range_name, safe='')}",
        token=token,
    )
    values = payload.get("values", []) if isinstance(payload, dict) else []
    return values if isinstance(values, list) else []


def _ensure_google_sheet_headers(spreadsheet_id: str, tab_name: str, token: str) -> None:
    existing = _read_google_sheet_values(spreadsheet_id, f"{tab_name}!1:1", token)
    if existing and existing[0] == GOOGLE_SHEET_HEADERS:
        return
    _request_json(
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{quote(f'{tab_name}!1:1', safe='')}?valueInputOption=RAW",
        method="PUT",
        token=token,
        body={"values": [GOOGLE_SHEET_HEADERS]},
    )

def _canonical_dossier(raw: dict[str, Any], source_file: str | None = None) -> dict[str, Any]:
    identity = raw.get("identity", {}) if isinstance(raw.get("identity"), dict) else {}
    historical = raw.get("historical_context", {}) if isinstance(raw.get("historical_context"), dict) else {}
    live = raw.get("live_intelligence", {}) if isinstance(raw.get("live_intelligence"), dict) else {}
    gateway = raw.get("gateway_evaluations", {}) if isinstance(raw.get("gateway_evaluations"), dict) else {}
    return {
        "identity": {
            "name": require_text(identity.get("name"), "identity.name"),
            "lead_id": identity.get("lead_id"),
            "linkedin_url": _clean_url(str(identity.get("linkedin_url") or "")),
            "alternative_urls": identity.get("alternative_urls") if isinstance(identity.get("alternative_urls"), list) else [],
            "identity_status": identity.get("identity_status"),
        },
        "historical_context": {
            "sources_found": historical.get("sources_found") if isinstance(historical.get("sources_found"), list) else [],
            "all_recorded_headlines": historical.get("all_recorded_headlines") if isinstance(historical.get("all_recorded_headlines"), list) else [],
            "raw_notes_and_reasoning": historical.get("raw_notes_and_reasoning") if isinstance(historical.get("raw_notes_and_reasoning"), list) else [],
            "legacy_highest_score": historical.get("legacy_highest_score"),
            "v2_triage_score": historical.get("v2_triage_score"),
            "v2_triage_reasoning": historical.get("v2_triage_reasoning"),
            "p1_quality_band": historical.get("p1_quality_band"),
            "p1_hard_gates": historical.get("p1_hard_gates") if isinstance(historical.get("p1_hard_gates"), dict) else {},
            "p1_triage_status": historical.get("p1_triage_status"),
            "p1_evidence_urls": historical.get("p1_evidence_urls") if isinstance(historical.get("p1_evidence_urls"), list) else [],
        },
        "live_intelligence": {
            "last_updated": live.get("last_updated"),
            "exa_raw_urls": live.get("exa_raw_urls") if isinstance(live.get("exa_raw_urls"), list) else [],
            "exa_snippets": live.get("exa_snippets") if isinstance(live.get("exa_snippets"), list) else [],
        },
        "gateway_evaluations": gateway,
        "outreach": raw.get("outreach", {}) if isinstance(raw.get("outreach"), dict) else {},
        "legacy_state": {"L2_State": raw.get("L2_State"), "source_file": source_file},
    }


def _exa_people_search(query: str, limit: int) -> list[dict[str, Any]]:
    key = require_env("EXA_API_KEY")
    payload = {
        "query": query,
        "numResults": limit,
        "useAutoprompt": True,
        "category": "people",
        "contents": {"text": {"maxCharacters": 1200}},
    }
    response = _request_json("https://api.exa.ai/search", method="POST", headers={"x-api-key": key}, body=payload)
    results = response.get("results")
    if not isinstance(results, list):
        raise P1WorkerInputError("Exa response missing results list")
    items = []
    for item in results[:limit]:
        title = str(item.get("title") or item.get("url") or "").strip()
        url = _clean_url(str(item.get("url") or ""))
        text = str(item.get("text") or item.get("summary") or "")[:1200].strip()
        if not title or not url:
            continue
        items.append({"name": _name_from_title(title), "headline": title, "source_url": url, "source": "exa", "evidence": [text or title]})
    return items


def _source_attempt_payload(source: str, request: dict[str, Any], result_count: int, cache: dict[str, Any], *, query: str | None = None, actor_id: str | None = None) -> dict[str, Any]:
    payload = {
        "source": source,
        "provider": source,
        "result_count": result_count,
        "attempt_count": 1,
        "retry_count": 0,
        "query_hash": _query_hash(request),
        "safe_query_summary": _safe_query_summary(query or request),
        **cache,
    }
    if actor_id:
        payload["actor_id"] = actor_id
    return payload


def _source_quality_by_source(
    source_batches: Any,
    normalized_leads: Any,
    triage_scores: Any,
    gateway_evaluations: Any,
) -> dict[str, dict[str, Any]]:
    quality: dict[str, dict[str, Any]] = {}
    for batch in source_batches if isinstance(source_batches, list) else []:
        if not isinstance(batch, dict):
            continue
        source = str(batch.get("source") or "unknown")
        raw_count = len(batch.get("lead_candidates", []) if isinstance(batch.get("lead_candidates"), list) else [])
        quality.setdefault(source, {"raw": 0, "normalized": 0, "triage_qualified": 0, "gateway_approved": 0})
        quality[source]["raw"] += raw_count
    for item in normalized_leads if isinstance(normalized_leads, list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown")
        quality.setdefault(source, {"raw": 0, "normalized": 0, "triage_qualified": 0, "gateway_approved": 0})
        quality[source]["normalized"] += 1
    for item in triage_scores if isinstance(triage_scores, list) else []:
        if not isinstance(item, dict):
            continue
        source = str(item.get("source") or "unknown")
        quality.setdefault(source, {"raw": 0, "normalized": 0, "triage_qualified": 0, "gateway_approved": 0})
        if isinstance(item.get("triage"), dict) and item["triage"].get("qualified") is True:
            quality[source]["triage_qualified"] += 1
    for item in gateway_evaluations if isinstance(gateway_evaluations, list) else []:
        if not isinstance(item, dict):
            continue
        source = _source_from_gateway_evaluation(item)
        quality.setdefault(source, {"raw": 0, "normalized": 0, "triage_qualified": 0, "gateway_approved": 0})
        if isinstance(item.get("gateway"), dict) and item["gateway"].get("decision") == "awaiting_outreach":
            quality[source]["gateway_approved"] += 1
    for stats in quality.values():
        raw = int(stats.get("raw") or 0)
        normalized = int(stats.get("normalized") or 0)
        triage = int(stats.get("triage_qualified") or 0)
        stats["normalized_rate"] = round(normalized / raw, 4) if raw else 0
        stats["triage_qualified_rate"] = round(triage / normalized, 4) if normalized else 0
        stats["gateway_approved_rate"] = round(int(stats.get("gateway_approved") or 0) / triage, 4) if triage else 0
    return quality


def _source_from_gateway_evaluation(item: dict[str, Any]) -> str:
    dossier = item.get("dossier") if isinstance(item.get("dossier"), dict) else {}
    identity = dossier.get("identity") if isinstance(dossier.get("identity"), dict) else {}
    if identity.get("source"):
        return str(identity["source"])
    historical_context = dossier.get("historical_context") if isinstance(dossier.get("historical_context"), dict) else {}
    sources_found = historical_context.get("sources_found") if isinstance(historical_context.get("sources_found"), list) else []
    for source in sources_found:
        value = str(source or "").strip()
        if value:
            return value
    return str(item.get("source") or "unknown")


def _with_provider_cache(inputs: dict[str, Any], source: str, request: dict[str, Any], fetch: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if _disable_provider_cache(inputs):
        items = fetch()
        return items, {"cache_enabled": False, "cache_hit": False}
    cache_dir = _provider_cache_dir(inputs)
    ttl_seconds = _provider_cache_ttl_seconds(inputs)
    key = _provider_cache_key(source, request)
    path = cache_dir / f"{key}.json"
    if path.exists():
        cached = _read_provider_cache(path, ttl_seconds)
        if cached is not None:
            return cached["items"], {
                "cache_enabled": True,
                "cache_hit": True,
                "cache_key": key,
                "cached_at": cached["cached_at"],
                "cache_path": str(path),
            }
    items = fetch()
    _write_provider_cache(path, source, request, items)
    return items, {"cache_enabled": True, "cache_hit": False, "cache_key": key, "cache_path": str(path)}


def _disable_provider_cache(inputs: dict[str, Any]) -> bool:
    value = inputs.get("use_provider_cache")
    if value is None:
        value = os.environ.get("P1_USE_PROVIDER_CACHE", "true")
    if isinstance(value, bool):
        return not value
    return str(value).strip().lower() in {"0", "false", "no", "off"}


def _provider_cache_dir(inputs: dict[str, Any]) -> Path:
    path = inputs.get("provider_cache_dir") or os.environ.get("P1_PROVIDER_CACHE_DIR") or ".cache/p1_provider_cache"
    return Path(require_text(str(path), "provider_cache_dir"))


def _provider_cache_ttl_seconds(inputs: dict[str, Any]) -> int:
    raw = inputs.get("provider_cache_ttl_seconds") or os.environ.get("P1_PROVIDER_CACHE_TTL_SECONDS") or P1_PROVIDER_CACHE_TTL_SECONDS
    ttl_seconds = int(raw)
    if ttl_seconds < 1:
        raise P1WorkerInputError("provider_cache_ttl_seconds must be >= 1")
    return ttl_seconds


def _provider_cache_key(source: str, request: dict[str, Any]) -> str:
    payload = json.dumps({"version": P1_PROVIDER_CACHE_VERSION, "source": source, "request": request}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _query_hash(payload: dict[str, Any] | str) -> str:
    raw = payload if isinstance(payload, str) else json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def _safe_query_summary(payload: dict[str, Any] | str) -> str:
    if isinstance(payload, str):
        return payload[:120]
    if "query" in payload:
        return str(payload.get("query") or "")[:120]
    if "actor_id" in payload:
        return f"actor={payload.get('actor_id')} limit={payload.get('limit')}"
    return json.dumps(payload, ensure_ascii=False, sort_keys=True)[:120]


def _provider_cache_inputs(inputs: dict[str, Any]) -> dict[str, Any]:
    excluded = {
        "allow_data_lake_write",
        "allow_google_sheet_write",
        "allow_outreach_master_write",
        "data_lake_dossier_path",
        "dossier_output_path",
        "outreach_master_path",
        "provider_cache_dir",
        "provider_cache_ttl_seconds",
        "require_human_approval",
        "use_provider_cache",
    }
    return {key: value for key, value in sorted(inputs.items()) if key not in excluded}


def _read_provider_cache(path: Path, ttl_seconds: int) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise P1WorkerInputError(f"P1 provider cache is corrupt: {path}") from exc
    if not isinstance(payload, dict) or payload.get("version") != P1_PROVIDER_CACHE_VERSION:
        raise P1WorkerInputError(f"P1 provider cache has invalid schema: {path}")
    cached_at = payload.get("cached_at")
    items = payload.get("items")
    if not isinstance(cached_at, (int, float)) or not isinstance(items, list):
        raise P1WorkerInputError(f"P1 provider cache has invalid payload: {path}")
    if time.time() - float(cached_at) > ttl_seconds:
        return None
    if not all(isinstance(item, dict) for item in items):
        raise P1WorkerInputError(f"P1 provider cache contains non-object items: {path}")
    return {"cached_at": cached_at, "items": items}


def _write_provider_cache(path: Path, source: str, request: dict[str, Any], items: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "version": P1_PROVIDER_CACHE_VERSION,
        "source": source,
        "request": request,
        "cached_at": time.time(),
        "items": items,
    }
    tmp_path = path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp_path.replace(path)


def _apify_funding_search(inputs: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    actor_input = {
        "mode": "all_sources",
        "searchQuery": str(inputs.get("apify_search_query") or "B2C"),
        "daysBack": int(inputs.get("days_back", 14)),
        "maxItems": limit,
        "maxResults": limit,
        "outputMode": "raw",
    }
    rows = _run_apify_actor("nexgendata/startup-funding-tracker", actor_input)
    candidates = []
    for row in rows[:limit]:
        company = row.get("companyName", "Unknown Startup")
        amount = row.get("fundingAmount", "Unknown")
        source_url = row.get("sourceUrl", "")
        investors = row.get("investors", [])
        if isinstance(investors, str):
            investors = [item.strip() for item in investors.split(",")]
        if not isinstance(investors, list):
            continue
        for investor in investors:
            name = str(investor).strip()
            if not name or _looks_like_company(name) or _is_institutional_investor(name):
                continue
            candidates.append({"name": name, "headline": f"Angel investor in {company} ({amount} round)", "source_url": source_url, "source": "apify_funding", "evidence": [json.dumps(row, ensure_ascii=False)[:1000]]})
            if len(candidates) >= limit:
                return candidates[:limit]
        if company and len(candidates) < limit:
            for founder in _exa_people_search(f"{company} founder LinkedIn {row.get('industry', '')}", 2):
                founder_url = _clean_url(str(founder.get("source_url") or founder.get("linkedin_url") or ""))
                if "linkedin.com/in/" not in founder_url:
                    continue
                candidate = {
                    **founder,
                    "headline": founder.get("headline") or f"Founder at {company}",
                    "source_url": founder_url,
                    "linkedin_url": founder_url,
                    "source": "apify_funding",
                    "evidence": [json.dumps(row, ensure_ascii=False)[:1000], *founder.get("evidence", [])],
                }
                candidates.append(candidate)
                if len(candidates) >= limit:
                    return candidates[:limit]
    return candidates[:limit]


def _apify_crunchbase_search(inputs: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    urls = inputs.get("crunchbase_start_urls") or [
        "https://www.crunchbase.com/person/naval-ravikant",
        "https://www.crunchbase.com/person/elad-gil",
        "https://www.crunchbase.com/person/lachy-groom",
    ]
    actor_input = {"startUrls": [{"url": str(url)} for url in urls[:limit]], "maxItems": limit}
    actor_id = str(inputs.get("crunchbase_actor_id") or "parseforge/crunchbase-scraper")
    rows = _run_apify_actor(actor_id, actor_input)
    candidates = []
    for row in rows[:limit]:
        name = str(row.get("name") or f"{row.get('first_name', '')} {row.get('last_name', '')}").strip()
        if not name:
            continue
        headline = str(row.get("primaryJobTitle") or row.get("primary_job_title") or "Angel Investor")
        org = str(row.get("primaryOrganization") or row.get("primary_organization") or "").strip()
        if org:
            headline = f"{headline} at {org}"
        candidates.append(
            {
                "name": name,
                "headline": headline,
                "linkedin_url": row.get("linkedinUrl") or row.get("linkedin_url") or "",
                "source_url": row.get("crunchbaseUrl") or row.get("url") or row.get("cbUrl") or "",
                "source": "apify_crunchbase",
                "evidence": [json.dumps(row, ensure_ascii=False)[:1000]],
            }
        )
    return candidates


def _apify_linkedin_search(inputs: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    actor_id = str(inputs.get("linkedin_actor_id") or "riceman/linkedin-sales-navigator-lead-search-scraper")
    actor_input: dict[str, Any] = {
        "limit": limit,
        "keywords": str(inputs.get("linkedin_keywords") or inputs.get("query") or "AI angel investor operator"),
    }
    for key in (
        "current_company_names",
        "past_company_names",
        "company_headcounts",
        "company_type",
        "functions",
        "title_keywords",
        "seniority_levels",
        "geo_codes",
        "industry_codes",
        "years_of_experience",
    ):
        if key in inputs:
            actor_input[key] = inputs[key]
    if "title_keywords" not in actor_input and "seniority_levels" not in actor_input:
        actor_input["seniority_levels"] = ["Owner/Partner", "CXO", "Vice President", "Director"]
    rows = _run_apify_actor(actor_id, actor_input)
    candidates = []
    for row in rows[:limit]:
        if not isinstance(row, dict):
            continue
        name = str(row.get("full_name") or row.get("fullName") or row.get("name") or f"{row.get('first_name', '')} {row.get('last_name', '')}").strip()
        linkedin_url = _clean_url(str(row.get("linkedin_url") or row.get("linkedinUrl") or row.get("profile_url") or row.get("profileUrl") or ""))
        if not name or not linkedin_url:
            continue
        headline = str(row.get("headline") or row.get("job_title") or row.get("jobTitle") or row.get("title") or "LinkedIn operator/investor").strip()
        candidates.append(
            {
                "name": name,
                "headline": headline,
                "linkedin_url": linkedin_url,
                "source_url": linkedin_url,
                "source": "apify_linkedin",
                "evidence": [json.dumps(row, ensure_ascii=False)[:1000]],
            }
        )
    return candidates


def _run_apify_actor(actor_id: str, actor_input: dict[str, Any]) -> list[dict[str, Any]]:
    token = require_env("APIFY_API_TOKEN")
    encoded_actor = actor_id.replace("/", "~")
    max_items = _apify_max_items(actor_input)
    run = _request_json(f"https://api.apify.com/v2/acts/{encoded_actor}/runs?token={quote(token)}&maxItems={max_items}", method="POST", body=actor_input, timeout=60)
    run_id = run.get("data", {}).get("id")
    if not run_id:
        raise P1WorkerInputError(f"Apify actor did not return run id: {actor_id}")
    deadline = time.monotonic() + int(actor_input.get("timeoutSeconds") or 420)
    latest = {}
    while time.monotonic() < deadline:
        latest = _request_json(f"https://api.apify.com/v2/actor-runs/{run_id}?token={quote(token)}", timeout=30).get("data", {})
        status = latest.get("status")
        if status == "SUCCEEDED":
            dataset_id = latest.get("defaultDatasetId")
            if not dataset_id:
                raise P1WorkerInputError(f"Apify run succeeded without dataset: {actor_id}")
            items = _request_json(f"https://api.apify.com/v2/datasets/{dataset_id}/items?token={quote(token)}&clean=true", timeout=60)
            return items if isinstance(items, list) else []
        if status in {"FAILED", "ABORTED", "TIMED-OUT"}:
            raise P1WorkerInputError(f"Apify actor failed: {actor_id} status={status}")
        time.sleep(5)
    raise P1WorkerInputError(f"Apify actor timed out: {actor_id} latest_status={latest.get('status')}")


def _apify_max_items(actor_input: dict[str, Any]) -> int:
    raw = actor_input.get("maxItems") or actor_input.get("maxResults") or actor_input.get("limit")
    try:
        max_items = int(raw)
    except (TypeError, ValueError) as exc:
        raise P1WorkerInputError("Apify actor input must include positive maxItems, maxResults, or limit") from exc
    if max_items < 1:
        raise P1WorkerInputError("Apify actor maxItems must be greater than zero")
    return max_items


def _gemini_client():
    return genai.Client(api_key=require_env("GEMINI_API_KEY"))


def _gemini_json(client: Any, prompt: str) -> dict[str, Any]:
    config = types.GenerateContentConfig(responseMimeType="application/json", temperature=0, maxOutputTokens=4096)
    attempts = [
        prompt,
        f"{prompt}\n\nReturn one complete valid JSON object only. Do not truncate. Do not use markdown fences.",
    ]
    last_text = ""
    for attempt_prompt in attempts:
        response = client.models.generate_content(model="gemini-2.5-flash", contents=attempt_prompt, config=config)
        text = str(response.text or "").strip()
        text = text.replace("```json", "").replace("```", "").strip()
        last_text = text
        try:
            parsed = json.loads(text)
            break
        except json.JSONDecodeError:
            continue
    else:
        raise P1WorkerInputError(f"Gemini returned invalid JSON after {len(attempts)} attempts: {last_text[:500]}")
    if not isinstance(parsed, dict):
        raise P1WorkerInputError("Gemini returned non-object JSON")
    return parsed


def _google_access_token(service_account_path: str) -> str:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    credentials = Credentials.from_service_account_file(service_account_path, scopes=scopes)
    credentials.refresh(GoogleAuthRequest())
    return require_text(credentials.token, "google access token")


def _request_json(
    url: str,
    *,
    method: str = "GET",
    headers: dict[str, str] | None = None,
    body: dict[str, Any] | None = None,
    token: str | None = None,
    timeout: int = HTTP_TIMEOUT_SECONDS,
) -> Any:
    request_headers = {"accept": "application/json", "user-agent": USER_AGENT}
    if headers:
        request_headers.update(headers)
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        request_headers["content-type"] = "application/json"
    if token:
        request_headers["authorization"] = f"Bearer {token}"
    request = Request(url, data=data, headers=request_headers, method=method)
    attempts = len(HTTP_GET_RETRY_DELAYS_SECONDS) + 1 if method == "GET" else 1
    for attempt in range(attempts):
        try:
            with urlopen(request, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except HTTPError as exc:
            if method == "GET" and exc.code in {429, 502, 503, 504} and attempt < attempts - 1:
                time.sleep(HTTP_GET_RETRY_DELAYS_SECONDS[attempt])
                continue
            error_body = _redact_secrets(exc.read().decode("utf-8", errors="replace")[:1000])
            safe_url = _redact_secrets(url)
            raise P1WorkerInputError(f"real HTTP request failed {method} {safe_url}: {exc.code}: {error_body}") from exc
        except URLError as exc:
            if method == "GET" and attempt < attempts - 1:
                time.sleep(HTTP_GET_RETRY_DELAYS_SECONDS[attempt])
                continue
            safe_url = _redact_secrets(url)
            raise P1WorkerInputError(f"real HTTP request failed {method} {safe_url}: {exc.reason}") from exc
    raise P1WorkerInputError(f"real HTTP request failed {method} {_redact_secrets(url)} after retries")


def _redact_secrets(value: str) -> str:
    redacted = re.sub(r"(?i)([?&]token=)[^&\s]+", r"\1[REDACTED]", value)
    redacted = re.sub(r"apify_api_[A-Za-z0-9_-]+", "apify_api_[REDACTED]", redacted)
    return redacted


def _clean_url(value: str) -> str:
    return value.strip().split("?")[0].rstrip("/")


def _linkedin_person_url_from_urls(urls: list[Any]) -> str:
    for value in urls:
        url = _clean_url(str(value or ""))
        if LINKEDIN_PERSON_RE.match(url):
            return url
    return ""


def _has_clean_person_name(name: str) -> bool:
    text = name.strip()
    if len(text) < 2 or len(text) > 80:
        return False
    allowed_punctuation = {" ", "-", "'", "’", "."}
    if any((not ch.isalpha()) and ch not in allowed_punctuation for ch in text):
        return False
    words = [word for word in re.split(r"[\s\-'.’]+", text) if word]
    return bool(words) and all(any(ch.isalpha() for ch in word) for word in words)


def _looks_like_company(name: str) -> bool:
    lowered = name.lower()
    tokens = ["ventures", "capital", "partners", "fund", "group", "inc", "llc", "ltd", "company", "combinator", "labs"]
    return any(token in lowered for token in tokens)


def _is_institutional_investor(name: str) -> bool:
    lowered = name.lower()
    institutions = {"y combinator", "techstars", "sequoia", "a16z", "andreessen horowitz", "accel", "index ventures"}
    return lowered in institutions


def _name_from_title(title: str) -> str:
    clean = re.split(r"[-|–—]", title)[0].strip()
    return clean[:80] if clean else title[:80]


def _slug(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", value.lower()).strip("_")
    return slug or "unknown_p1_dossier"


def _metrics_summary(metrics: dict[str, Any]) -> str:
    return (
        f"P1 funnel: raw {metrics['raw_leads']} -> normalized {metrics['normalized_leads']} -> "
        f"triage qualified {metrics['triage_qualified']} -> gateway approved {metrics['gateway_approved']} -> "
        f"drafted {metrics['drafted']} -> sheet {metrics['sheet_written']} / "
        f"data lake {metrics['data_lake_written']} / outreach master {metrics['outreach_master_written']}."
    )


def _normalize_claims(value: Any, evidence_urls: list[Any]) -> list[dict[str, Any]]:
    if isinstance(value, list) and value:
        claims = []
        for item in value:
            if isinstance(item, dict):
                text = str(item.get("text") or item.get("claim_text") or "").strip()
                source_url = str(item.get("source_url") or (evidence_urls[0] if evidence_urls else "")).strip()
                if text and source_url:
                    claims.append({"text": text, "source_url": source_url, "evidence_urls": evidence_urls})
        if claims:
            return claims
    return [{"text": "Outreach draft is based on the dossier and live intelligence evidence.", "source_url": str(evidence_urls[0]), "evidence_urls": evidence_urls}] if evidence_urls else []


def _ensure_abrt_or_limpid_mention(text: str) -> str:
    lowered = text.lower()
    if "abrt" in lowered or "limpid" in lowered:
        return text
    return f"{text.rstrip()} At ABRT, we're comparing notes with operators building this kind of AI-native edge."


def _normalize_outreach_text(text: str) -> str:
    cleaned = _remove_placeholder_signoff(text)
    cleaned = _ensure_abrt_or_limpid_mention(cleaned)
    cleaned = _ensure_send_ready_cta(cleaned)
    return _remove_placeholder_signoff(cleaned)


def _remove_placeholder_signoff(text: str) -> str:
    stripped = re.sub(r"(\s+|\n+)(best|thanks|regards),\s*$", "", text.rstrip(), flags=re.IGNORECASE)
    lines = stripped.rstrip().splitlines()
    while lines and lines[-1].strip().lower() in {"best,", "thanks,", "regards,"}:
        lines.pop()
    return "\n".join(lines).rstrip()


def _ensure_send_ready_cta(text: str) -> str:
    if _has_clear_cta(text):
        return text
    return f"{text.rstrip()} Would a quick 30-minute call next week make sense?"


def _has_clear_cta(text: str) -> bool:
    return _meeting_cta_count(text) == 1


def _meeting_cta_count(text: str) -> int:
    normalized = re.sub(r"\s+", " ", text.strip().lower())
    meeting_action_re = re.compile(r"\b(call|chat|connect|meet|meeting|conversation)\b")
    timing_re = re.compile(r"\b(next week|30\s*[- ]?minutes?|30\s*min|quick|brief)\b")
    count = 0
    for sentence_match in re.finditer(r"[^.!?\n]+", normalized):
        sentence = sentence_match.group(0)
        for action_match in meeting_action_re.finditer(sentence):
            start, end = action_match.span()
            local_window = sentence[max(0, start - 50) : min(len(sentence), end + 80)]
            if timing_re.search(local_window):
                count += 1
    return count


def _has_placeholder_signoff(text: str) -> bool:
    stripped = text.strip().lower()
    return stripped.endswith('best,') or stripped.endswith('thanks,') or stripped.endswith('regards,')


def _claims_have_sources(draft: dict[str, Any]) -> bool:
    claims = draft.get("claims")
    if not isinstance(claims, list) or not claims:
        return False
    for claim in claims:
        if not isinstance(claim, dict) or not str(claim.get("text") or "").strip() or not str(claim.get("source_url") or "").strip():
            return False
    return True


def _draft_has_verified_person_linkedin(draft: dict[str, Any]) -> bool:
    linkedin_url = _clean_url(str(draft.get("linkedin_url") or ""))
    identity_status = str(draft.get("identity_status") or "").strip()
    return bool(LINKEDIN_PERSON_RE.match(linkedin_url)) and identity_status == IDENTITY_STATUS_VERIFIED


def _draft_linkedin_has_evidence(draft: dict[str, Any]) -> bool:
    linkedin_url = _canonical_linkedin_url(str(draft.get("linkedin_url") or ""))
    if not linkedin_url:
        return False
    evidence_urls = draft.get("evidence_urls")
    claim_urls = [
        str(claim.get("source_url") or "")
        for claim in (draft.get("claims") if isinstance(draft.get("claims"), list) else [])
        if isinstance(claim, dict)
    ]
    urls = [*(evidence_urls if isinstance(evidence_urls, list) else []), *claim_urls]
    return any(_canonical_linkedin_url(str(url)) == linkedin_url for url in urls)


def _draft_has_live_linkedin_profile(draft: dict[str, Any]) -> bool:
    linkedin_url = _clean_url(str(draft.get("linkedin_url") or ""))
    return _linkedin_profile_url_is_live(linkedin_url)


def _linkedin_profile_url_is_live(linkedin_url: str) -> bool:
    url = _clean_url(linkedin_url)
    if not LINKEDIN_PERSON_RE.match(url):
        return False
    request = Request(url, headers={"User-Agent": "Mozilla/5.0 (compatible; ABRT-P1-LinkVerifier/1.0)"})
    try:
        with urlopen(request, timeout=15) as response:
            status = int(getattr(response, "status", 0) or response.getcode())
            body = response.read(750_000).decode("utf-8", errors="ignore").lower()
    except (HTTPError, URLError, TimeoutError, OSError):
        return False
    if status != 200:
        return False
    if "profile not found | linkedin" in body or "profile not found" in body:
        return False
    title_match = re.search(r"<title[^>]*>(.*?)</title>", body, flags=re.IGNORECASE | re.DOTALL)
    if not title_match:
        return False
    title = re.sub(r"\s+", " ", title_match.group(1)).strip().lower()
    return bool(title and title != "linkedin" and "profile not found" not in title)


def _canonical_linkedin_url(url: str) -> str:
    cleaned = _clean_url(url).split("?")[0].rstrip("/")
    if not LINKEDIN_PERSON_RE.match(cleaned):
        return ""
    return re.sub(r"^https?://(?:(?:www|[a-z]{2})\.)?linkedin\.com/", "linkedin.com/", cleaned, flags=re.IGNORECASE).lower()


HANDLERS = {
    "p1-dossier-reader": read_existing_dossiers,
    "p1-source-collector": collect_sources,
    "p1-lead-normalizer": normalize_leads,
    "p1-source-merger": merge_source_batches,
    "p1-triage-scorer": score_triage,
    "p1-dossier-writer": write_dossiers,
    "p1-live-intel-gatherer": gather_live_intelligence,
    "p1-gateway-evaluator": evaluate_gateway,
    "p1-forge-queue-builder": build_forge_queue,
    "p1-outreach-draft-writer": write_outreach_drafts,
    "p1-outreach-quality-judge": judge_outreach_quality,
    "p1-data-lake-syncer": sync_data_lake,
    "p1-outreach-master-syncer": sync_outreach_master,
    "p1-google-sheets-syncer": sync_google_sheets,
    "p1-metrics-reporter": build_metrics_report,
    "read_existing_dossiers": read_existing_dossiers,
    "collect_sources": collect_sources,
    "normalize_leads": normalize_leads,
    "merge_source_batches": merge_source_batches,
    "score_triage": score_triage,
    "write_dossiers": write_dossiers,
    "gather_live_intelligence": gather_live_intelligence,
    "evaluate_gateway": evaluate_gateway,
    "build_forge_queue": build_forge_queue,
    "write_outreach_drafts": write_outreach_drafts,
    "judge_outreach_quality": judge_outreach_quality,
    "sync_data_lake": sync_data_lake,
    "sync_outreach_master": sync_outreach_master,
    "sync_google_sheets": sync_google_sheets,
    "build_metrics_report": build_metrics_report,
}


def main() -> None:
    request = json.loads(sys.stdin.read())
    work_order = request["work_order"]
    handler_key = work_order["worker_profile"]
    if handler_key not in HANDLERS:
        handler_key = work_order["task_type"]
    if handler_key not in HANDLERS:
        raise SystemExit(f"unknown P1 worker_profile/task_type: {work_order['worker_profile']} / {work_order['task_type']}")
    try:
        result = HANDLERS[handler_key](work_order, request["context"])
    except P1WorkerInputError as exc:
        sys.stderr.write(json.dumps({"error_type": "P1WorkerInputError", "message": str(exc)}, ensure_ascii=True))
        raise SystemExit(2) from None
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
