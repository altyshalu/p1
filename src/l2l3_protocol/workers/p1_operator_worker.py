from __future__ import annotations

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


HTTP_TIMEOUT_SECONDS = 30
USER_AGENT = "l2l3-protocol/0.1 real-p1-operator-outreach"


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
        if source == "exa":
            items = _exa_people_search(query, min(limit, 10))
            attempts.append({"source": source, "query": query, "result_count": len(items)})
            candidates.extend(items)
        elif source == "apify_funding":
            items = _apify_funding_search(inputs, min(limit, 10))
            attempts.append({"source": source, "result_count": len(items)})
            candidates.extend(items)
        elif source == "apify_crunchbase":
            items = _apify_crunchbase_search(inputs, min(limit, 5))
            attempts.append({"source": source, "result_count": len(items)})
            candidates.extend(items)
        elif source == "apify_linkedin":
            items = _apify_linkedin_search(inputs, min(limit, 100))
            attempts.append({"source": source, "result_count": len(items)})
            candidates.extend(items)
        else:
            raise P1WorkerInputError(f"unsupported P1 source: {source}")
    if not candidates:
        raise P1WorkerInputError(f"real P1 sourcing returned no lead candidates for sources={sources}")
    return {"lead_candidates": candidates[:limit], "source_attempts": attempts}


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
        url = _clean_url(str(candidate.get("linkedin_url") or candidate.get("source_url") or ""))
        dedupe_key = (url or name).lower()
        if dedupe_key in seen:
            rejected.append({"reason": "duplicate", "candidate": candidate})
            continue
        seen.add(dedupe_key)
        normalized.append(
            {
                "name": name,
                "headline": str(candidate.get("headline") or "Angel investor / operator").strip(),
                "linkedin_url": url if "linkedin.com/in/" in url else "",
                "source_url": _clean_url(str(candidate.get("source_url") or url)),
                "source": str(candidate.get("source") or "unknown"),
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
- b2c_dna_score: 0-45 for B2C, PLG, consumer, product-led, viral, mobile, fintech, gaming, marketplace, or SMB bottom-up SaaS DNA.
- investor_score: 0-35 for explicit angel investing, syndicate, portfolio, exits, or capital potential.
- systematic_score: 0-20 for data-driven, AI, ML, quant, systematic, framework, evidence, metrics, product ops, analytics.
- is_blacklist true for military, biotech-only, academic-only, legal-only, heavy industry.
Return JSON only with keys: b2c_dna_score, investor_score, systematic_score, is_blacklist, reasoning.
""",
        )
        total = int(response.get("b2c_dna_score", 0)) + int(response.get("investor_score", 0)) + int(response.get("systematic_score", 0))
        if response.get("is_blacklist") is True:
            total = 0
        scores.append({**lead, "triage": {**response, "total_score": total, "qualified": total >= 50}})
    return {"triage_scores": scores}


def write_dossiers(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    scores = require_list(work_order["inputs"].get("triage_scores"), "triage_scores")
    dossiers = []
    rejected = []
    for item in scores:
        triage = item.get("triage") if isinstance(item.get("triage"), dict) else {}
        if not triage.get("qualified"):
            rejected.append({"name": item.get("name"), "reason": "triage_below_threshold", "score": triage.get("total_score")})
            continue
        dossiers.append(
            {
                "identity": {
                    "name": item["name"],
                    "linkedin_url": item.get("linkedin_url", ""),
                    "alternative_urls": [item.get("source_url")] if item.get("source_url") and item.get("source_url") != item.get("linkedin_url") else [],
                },
                "historical_context": {
                    "sources_found": [item.get("source", "runtime_source")],
                    "all_recorded_headlines": [item.get("headline", "")],
                    "raw_notes_and_reasoning": [triage.get("reasoning", "")],
                    "v2_triage_score": triage.get("total_score"),
                    "v2_triage_reasoning": triage.get("reasoning", ""),
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
        updated.append(canonical)
    return {"p1_dossiers": updated}


def evaluate_gateway(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    client = _gemini_client()
    dossiers = require_list(work_order["inputs"].get("p1_dossiers"), "p1_dossiers")
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
- bandwidth_signal HIGH only for advisors, angel investors, solo/fractional/stealth builders, independent operators, or not currently overloaded.
- bandwidth_signal LOW for active C-suite/VP/Director/Partner/GP at substantial operating company.
- liquidity_signal YES when unicorn/major exit/known high-growth operator/investor evidence exists.
- systematic_alignment YES when data/AI/product/scaling/systematic evidence exists.
Return JSON only with keys: identity_confidence, bandwidth_signal, liquidity_signal, systematic_alignment, current_role_verified, mythos_dossier.
""",
        )
        confidence = int(response.get("identity_confidence", 0))
        bandwidth = str(response.get("bandwidth_signal", "UNKNOWN")).upper()
        liquidity = str(response.get("liquidity_signal", "UNKNOWN")).upper()
        if confidence < 90:
            decision = "identity_mismatch"
        elif bandwidth == "LOW" or liquidity == "NO":
            decision = "bypass"
        elif bandwidth == "HIGH":
            decision = "awaiting_outreach"
        else:
            decision = "needs_more_evidence"
        evaluations.append({"dossier": dossier, "gateway": {**response, "decision": decision}})
    return {"gateway_evaluations": evaluations}


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
        draft = {
            "name": dossier["identity"]["name"],
            "linkedin_url": dossier["identity"].get("linkedin_url", ""),
            "current_role": gateway.get("current_role_verified", ""),
            "archetype": response.get("archetype"),
            "text": require_text(response.get("draft"), "draft"),
            "evidence_urls": evidence_urls,
            "claims": _normalize_claims(response.get("claims"), evidence_urls),
            "status": "draft",
            "publish": False,
        }
        drafts.append(draft)
    return {"outreach_drafts": drafts}


def judge_outreach_quality(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    drafts = require_list(work_order["inputs"].get("outreach_drafts"), "outreach_drafts")
    reasons: list[str] = []
    checks = {
        "has_drafts": bool(drafts),
        "all_have_text": all(isinstance(item.get("text"), str) and item["text"].strip() for item in drafts),
        "all_have_evidence_urls": all(isinstance(item.get("evidence_urls"), list) and item["evidence_urls"] for item in drafts),
        "all_claims_have_sources": all(_claims_have_sources(item) for item in drafts),
        "no_publish_external_action": all(item.get("publish") is not True and item.get("status") == "draft" for item in drafts),
        "word_count_under_110": all(len(str(item.get("text", "")).split()) <= 110 for item in drafts),
        "mentions_abrt_or_limpid": all(("abrt" in str(item.get("text", "")).lower()) or ("limpid" in str(item.get("text", "")).lower()) for item in drafts),
    }
    for key, passed in checks.items():
        if not passed:
            reasons.append(key)
    score = sum(1 for passed in checks.values() if passed) / len(checks)
    return {"passed": all(checks.values()), "score": score, "reasons": reasons, "checks": checks, "approval_package": {"outreach_drafts": drafts, "approval_required": True}}


def sync_google_sheets(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not bool(work_order["inputs"].get("allow_google_sheet_write", False)):
        raise P1WorkerInputError("Google Sheets sync requested without allow_google_sheet_write=true")
    spreadsheet_id = str(work_order["inputs"].get("spreadsheet_id") or os.environ.get("P1_GOOGLE_SHEET_ID") or "").strip()
    if not spreadsheet_id:
        raise P1WorkerInputError("missing required spreadsheet_id or P1_GOOGLE_SHEET_ID")
    service_account_path = str(work_order["inputs"].get("google_service_account_path") or os.environ.get("GOOGLE_SA_PATH") or "").strip()
    if not service_account_path:
        raise P1WorkerInputError("missing required google_service_account_path or GOOGLE_SA_PATH")
    drafts = require_list(work_order["inputs"].get("approval_package", {}).get("outreach_drafts") or work_order["inputs"].get("outreach_drafts"), "outreach_drafts")
    token = _google_access_token(service_account_path)
    range_name = quote("04_THE_FORGE_FINAL!A:J", safe="")
    values = [
        [
            draft.get("name", ""),
            draft.get("linkedin_url", ""),
            "RUNTIME_CONFIRMED",
            draft.get("current_role", ""),
            draft.get("text", ""),
            "",
            "",
            "",
            "Drafted",
            "\n".join(str(url) for url in draft.get("evidence_urls", [])),
        ]
        for draft in drafts
    ]
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{range_name}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS"
    payload = _request_json(url, method="POST", token=token, body={"values": values})
    return {
        "sync_result": {"spreadsheet_id": spreadsheet_id, "updated_range": payload.get("updates", {}).get("updatedRange"), "row_count": len(values)},
        "external_actions": [{"type": "google_sheets_append", "spreadsheet_id": spreadsheet_id, "row_count": len(values)}],
    }


def sync_data_lake(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    if not bool(work_order["inputs"].get("allow_data_lake_write", False)):
        raise P1WorkerInputError("Data Lake sync requested without allow_data_lake_write=true")
    output_path = (
        work_order["inputs"].get("data_lake_dossier_path")
        or work_order["inputs"].get("dossier_output_path")
        or os.environ.get("P1_DOSSIER_OUTPUT_PATH")
        or os.environ.get("P1_DOSSIER_SOURCE_PATH")
    )
    root = Path(require_text(output_path, "data_lake_dossier_path"))
    root.mkdir(parents=True, exist_ok=True)
    if not root.is_dir():
        raise P1WorkerInputError(f"data_lake_dossier_path is not a directory: {root}")
    dossiers = require_list(work_order["inputs"].get("p1_dossiers"), "p1_dossiers")
    written = []
    for dossier in dossiers:
        canonical = _canonical_dossier({**dossier, "runtime_source": "p1-operator-outreach"})
        payload = {**canonical, "runtime_source": "p1-operator-outreach", "updated_at": time.strftime("%Y-%m-%d %H:%M:%S")}
        name = payload["identity"]["name"]
        path = root / f"{_slug(name)}.json"
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        written.append({"name": name, "path": str(path)})
    return {
        "sync_result": {"target_path": str(root), "written_count": len(written), "files": written},
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
    additions = []
    for draft in drafts:
        if not isinstance(draft, dict):
            raise P1WorkerInputError("outreach_drafts must contain objects")
        item = {
            **draft,
            "runtime_source": "p1-operator-outreach",
            "synced_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "status": draft.get("status") or "draft",
            "publish": False,
        }
        additions.append(item)
    existing["drafts"] = [*existing_drafts, *additions]
    master_path.write_text(json.dumps(existing, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return {
        "sync_result": {"path": str(master_path), "written_count": len(additions), "total_drafts": len(existing["drafts"])},
        "external_actions": [{"type": "outreach_master_json_append", "path": str(master_path), "written_count": len(additions)}],
    }


def build_metrics_report(work_order: dict[str, Any], context: dict[str, Any]) -> dict[str, Any]:
    inputs = work_order["inputs"]
    lead_candidates = inputs.get("lead_candidates", [])
    normalized_leads = inputs.get("normalized_leads", [])
    rejected_leads = inputs.get("rejected_leads", [])
    triage_scores = inputs.get("triage_scores", [])
    dossiers = inputs.get("p1_dossiers", [])
    gateway_evaluations = inputs.get("gateway_evaluations", [])
    outreach_drafts = inputs.get("outreach_drafts", [])
    quality_eval = inputs.get("quality_eval", {})
    sync_results = inputs.get("external_sync_results", {})
    if not isinstance(sync_results, dict):
        sync_results = {}
    triage_qualified = [
        item
        for item in triage_scores
        if isinstance(item, dict) and isinstance(item.get("triage"), dict) and item["triage"].get("qualified") is True
    ]
    triage_rejected = [
        item
        for item in triage_scores
        if isinstance(item, dict) and isinstance(item.get("triage"), dict) and item["triage"].get("qualified") is not True
    ]
    gateway_approved = [
        item
        for item in gateway_evaluations
        if isinstance(item, dict) and isinstance(item.get("gateway"), dict) and item["gateway"].get("decision") == "awaiting_outreach"
    ]
    gateway_rejected = [
        item
        for item in gateway_evaluations
        if isinstance(item, dict) and isinstance(item.get("gateway"), dict) and item["gateway"].get("decision") != "awaiting_outreach"
    ]
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
        "data_lake_written": int((sync_results.get("data_lake") or {}).get("written_count") or 0),
        "outreach_master_written": int((sync_results.get("outreach_master") or {}).get("written_count") or 0),
    }
    return {"metrics": metrics, "summary": _metrics_summary(metrics)}


def _canonical_dossier(raw: dict[str, Any], source_file: str | None = None) -> dict[str, Any]:
    identity = raw.get("identity", {}) if isinstance(raw.get("identity"), dict) else {}
    historical = raw.get("historical_context", {}) if isinstance(raw.get("historical_context"), dict) else {}
    live = raw.get("live_intelligence", {}) if isinstance(raw.get("live_intelligence"), dict) else {}
    gateway = raw.get("gateway_evaluations", {}) if isinstance(raw.get("gateway_evaluations"), dict) else {}
    return {
        "identity": {
            "name": require_text(identity.get("name"), "identity.name"),
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
    payload = {"query": query, "numResults": limit, "useAutoprompt": True, "category": "auto"}
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


def _apify_funding_search(inputs: dict[str, Any], limit: int) -> list[dict[str, Any]]:
    actor_input = {
        "mode": "all_sources",
        "searchQuery": str(inputs.get("apify_search_query") or "B2C"),
        "daysBack": int(inputs.get("days_back", 14)),
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
    run = _request_json(f"https://api.apify.com/v2/acts/{encoded_actor}/runs?token={quote(token)}", method="POST", body=actor_input, timeout=60)
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


def _gemini_client():
    return genai.Client(api_key=require_env("GEMINI_API_KEY"))


def _gemini_json(client: Any, prompt: str) -> dict[str, Any]:
    response = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
    text = str(response.text or "").strip()
    text = text.replace("```json", "").replace("```", "").strip()
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as exc:
        raise P1WorkerInputError(f"Gemini returned invalid JSON: {text[:500]}") from exc
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
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        error_body = _redact_secrets(exc.read().decode("utf-8", errors="replace")[:1000])
        safe_url = _redact_secrets(url)
        raise P1WorkerInputError(f"real HTTP request failed {method} {safe_url}: {exc.code}: {error_body}") from exc
    except URLError as exc:
        safe_url = _redact_secrets(url)
        raise P1WorkerInputError(f"real HTTP request failed {method} {safe_url}: {exc.reason}") from exc


def _redact_secrets(value: str) -> str:
    redacted = re.sub(r"(?i)([?&]token=)[^&\s]+", r"\1[REDACTED]", value)
    redacted = re.sub(r"apify_api_[A-Za-z0-9_-]+", "apify_api_[REDACTED]", redacted)
    return redacted


def _clean_url(value: str) -> str:
    return value.strip().split("?")[0].rstrip("/")


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


def _claims_have_sources(draft: dict[str, Any]) -> bool:
    claims = draft.get("claims")
    if not isinstance(claims, list) or not claims:
        return False
    for claim in claims:
        if not isinstance(claim, dict) or not str(claim.get("text") or "").strip() or not str(claim.get("source_url") or "").strip():
            return False
    return True


HANDLERS = {
    "p1-dossier-reader": read_existing_dossiers,
    "p1-source-collector": collect_sources,
    "p1-lead-normalizer": normalize_leads,
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
