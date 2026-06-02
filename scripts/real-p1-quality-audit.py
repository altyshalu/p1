#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from p1_real_common import assert_summary_shape, request_json, require_capabilities, require_health

P1_PLAYBOOK_KEY = "p1-operator-outreach"
DEFAULT_JSON_OUTPUT = ROOT / "docs" / "reports" / "p1-quality-audit-pack.json"
DEFAULT_MARKDOWN_OUTPUT = ROOT / "docs" / "reports" / "p1-quality-audit-pack.md"

ARTIFACT_KEYS = {
    "source_batches": "p1_source_batch",
    "lead_candidates": "p1_lead_candidates",
    "normalized_leads": "p1_normalized_leads",
    "triage_scores": "p1_triage_scores",
    "p1_dossiers": "p1_dossiers",
    "gateway_evaluations": "p1_gateway_evaluations",
    "outreach_drafts": "p1_outreach_drafts",
    "approval_package": "p1_outreach_approval_package",
    "approval_preview": "p1_external_action_preview",
    "google_sheets_sync": "p1_external_sync_result",
    "data_lake_sync": "p1_data_lake_sync_result",
    "outreach_master_sync": "p1_outreach_master_sync_result",
    "metrics_report": "p1_metrics_report",
}

GENERIC_PHRASES = (
    "i came across your profile",
    "impressed by your background",
    "your impressive background",
    "thought you might be interested",
    "quick note",
    "would love to connect",
)


def latest_payload(run: dict[str, Any], artifact_type: str) -> dict[str, Any]:
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, list):
        return {}
    for artifact in reversed(artifacts):
        if not isinstance(artifact, dict) or artifact.get("artifact_type") != artifact_type:
            continue
        payload = artifact.get("payload")
        return payload if isinstance(payload, dict) else {}
    return {}


def payloads(run: dict[str, Any], artifact_type: str) -> list[dict[str, Any]]:
    artifacts = run.get("artifacts")
    if not isinstance(artifacts, list):
        return []
    found: list[dict[str, Any]] = []
    for artifact in artifacts:
        if not isinstance(artifact, dict) or artifact.get("artifact_type") != artifact_type:
            continue
        payload = artifact.get("payload")
        if isinstance(payload, dict):
            found.append(payload)
    return found


def list_value(payload: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = payload.get(key)
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def clean_string(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) and value.strip() else ""


def lead_name(item: dict[str, Any]) -> str:
    identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
    dossier = item.get("dossier") if isinstance(item.get("dossier"), dict) else {}
    dossier_identity = dossier.get("identity") if isinstance(dossier.get("identity"), dict) else {}
    return (
        clean_string(item.get("name"))
        or clean_string(identity.get("name"))
        or clean_string(dossier_identity.get("name"))
        or clean_string(item.get("lead_id"))
        or "unknown"
    )


def lead_id(item: dict[str, Any]) -> str:
    identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
    dossier = item.get("dossier") if isinstance(item.get("dossier"), dict) else {}
    dossier_identity = dossier.get("identity") if isinstance(dossier.get("identity"), dict) else {}
    return clean_string(item.get("lead_id")) or clean_string(identity.get("lead_id")) or clean_string(dossier_identity.get("lead_id")) or lead_name(item)


def linkedin_url(item: dict[str, Any]) -> str:
    identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
    dossier = item.get("dossier") if isinstance(item.get("dossier"), dict) else {}
    dossier_identity = dossier.get("identity") if isinstance(dossier.get("identity"), dict) else {}
    return clean_string(item.get("linkedin_url")) or clean_string(identity.get("linkedin_url")) or clean_string(dossier_identity.get("linkedin_url"))


def evidence_urls(item: dict[str, Any]) -> list[str]:
    urls: list[str] = []
    for key in ("evidence_urls", "source_urls", "sources_found"):
        value = item.get(key)
        if isinstance(value, list):
            urls.extend(clean_string(url) for url in value)
    gateway = item.get("gateway") if isinstance(item.get("gateway"), dict) else {}
    value = gateway.get("evidence_urls")
    if isinstance(value, list):
        urls.extend(clean_string(url) for url in value)
    triage = item.get("triage") if isinstance(item.get("triage"), dict) else {}
    value = triage.get("evidence_urls")
    if isinstance(value, list):
        urls.extend(clean_string(url) for url in value)
    identity = item.get("identity") if isinstance(item.get("identity"), dict) else {}
    historical = item.get("historical_context") if isinstance(item.get("historical_context"), dict) else {}
    for value in (identity.get("evidence_urls"), historical.get("sources_found"), historical.get("evidence_urls"), historical.get("p1_evidence_urls")):
        if isinstance(value, list):
            urls.extend(clean_string(url) for url in value)
    draft_claims = item.get("claims")
    if isinstance(draft_claims, list):
        for claim in draft_claims:
            if isinstance(claim, dict):
                urls.append(clean_string(claim.get("source_url")))
    return sorted({url for url in urls if url})


def source_domains(urls: list[str]) -> list[str]:
    domains: set[str] = set()
    for url in urls:
        parsed = urlparse(url)
        host = (parsed.netloc or "").lower()
        if "@" in host:
            host = host.rsplit("@", 1)[-1]
        if ":" in host:
            host = host.split(":", 1)[0]
        if host.startswith("www."):
            host = host[4:]
        domains.add(host or url.strip().lower())
    return sorted(domains)


def first_n(items: list[str], limit: int = 12) -> list[str]:
    return items[:limit]


def collect_p1_payloads(run: dict[str, Any]) -> dict[str, Any]:
    source_batches = payloads(run, ARTIFACT_KEYS["source_batches"])
    return {
        "source_batches": source_batches,
        "lead_candidates": list_value(latest_payload(run, ARTIFACT_KEYS["lead_candidates"]), "lead_candidates"),
        "normalized_leads": list_value(latest_payload(run, ARTIFACT_KEYS["normalized_leads"]), "normalized_leads"),
        "rejected_leads": list_value(latest_payload(run, ARTIFACT_KEYS["normalized_leads"]), "rejected_leads"),
        "triage_scores": list_value(latest_payload(run, ARTIFACT_KEYS["triage_scores"]), "triage_scores"),
        "p1_dossiers": list_value(latest_payload(run, ARTIFACT_KEYS["p1_dossiers"]), "p1_dossiers"),
        "gateway_evaluations": list_value(latest_payload(run, ARTIFACT_KEYS["gateway_evaluations"]), "gateway_evaluations"),
        "outreach_drafts": list_value(latest_payload(run, ARTIFACT_KEYS["outreach_drafts"]), "outreach_drafts"),
        "approval_package": latest_payload(run, ARTIFACT_KEYS["approval_package"]),
        "approval_preview": latest_payload(run, ARTIFACT_KEYS["approval_preview"]),
        "google_sheets_sync": latest_payload(run, ARTIFACT_KEYS["google_sheets_sync"]),
        "data_lake_sync": latest_payload(run, ARTIFACT_KEYS["data_lake_sync"]),
        "outreach_master_sync": latest_payload(run, ARTIFACT_KEYS["outreach_master_sync"]),
        "metrics_report": latest_payload(run, ARTIFACT_KEYS["metrics_report"]),
    }


def funnel_counts(payload: dict[str, Any], summary: dict[str, Any]) -> dict[str, int]:
    metrics = summary.get("latest_metrics") if isinstance(summary.get("latest_metrics"), dict) else {}
    counts = {
        "raw_leads": int(metrics.get("raw_leads") or len(payload["lead_candidates"]) or sum(len(list_value(batch, "lead_candidates")) for batch in payload["source_batches"])),
        "normalized_leads": int(metrics.get("normalized_leads") or len(payload["normalized_leads"])),
        "rejected_leads": int(metrics.get("rejected_leads") or len(payload["rejected_leads"])),
        "triage_qualified": int(metrics.get("triage_qualified") or 0),
        "triage_total": len(payload["triage_scores"]),
        "gateway_approved": int(metrics.get("gateway_approved") or 0),
        "gateway_total": len(payload["gateway_evaluations"]),
        "dossiers": int(metrics.get("dossiers") or len(payload["p1_dossiers"])),
        "drafts": int(metrics.get("drafted") or len(payload["outreach_drafts"])),
        "sheet_written": int(metrics.get("sheet_written") or 0),
        "data_lake_written": int(metrics.get("data_lake_written") or 0),
        "outreach_master_written": int(metrics.get("outreach_master_written") or 0),
    }
    if counts["triage_qualified"] == 0 and payload["triage_scores"]:
        counts["triage_qualified"] = sum(1 for item in payload["triage_scores"] if isinstance(item.get("triage"), dict) and item["triage"].get("qualified") is True)
    if counts["gateway_approved"] == 0 and payload["gateway_evaluations"]:
        counts["gateway_approved"] = sum(1 for item in payload["gateway_evaluations"] if isinstance(item.get("gateway"), dict) and item["gateway"].get("decision") == "awaiting_outreach")
    return counts


def artifact_presence(run: dict[str, Any], summary: dict[str, Any]) -> dict[str, bool]:
    artifact_counts = summary.get("artifact_counts") if isinstance(summary.get("artifact_counts"), dict) else {}
    return {name: int(artifact_counts.get(artifact_type) or 0) > 0 or bool(latest_payload(run, artifact_type)) for name, artifact_type in ARTIFACT_KEYS.items()}


def funnel_findings(payload: dict[str, Any], counts: dict[str, int], presence: dict[str, bool]) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    required_artifacts = ("lead_candidates", "normalized_leads", "triage_scores", "p1_dossiers", "gateway_evaluations", "outreach_drafts")
    for key in required_artifacts:
        if not presence[key]:
            findings.append({"severity": "blocker", "code": f"missing_artifact:{ARTIFACT_KEYS[key]}", "message": f"Missing required P1 artifact: {ARTIFACT_KEYS[key]}", "lead_ids": []})
    if counts["raw_leads"] > 0 and counts["normalized_leads"] == 0:
        findings.append({"severity": "blocker", "code": "zero_normalized_after_raw", "message": "Raw leads exist but no normalized leads were produced.", "lead_ids": []})
    if counts["normalized_leads"] > 0 and counts["triage_total"] == 0:
        findings.append({"severity": "blocker", "code": "zero_triage_after_normalized", "message": "Normalized leads exist but no triage scores were produced.", "lead_ids": []})
    if counts["triage_qualified"] > 0 and counts["dossiers"] == 0:
        findings.append({"severity": "blocker", "code": "zero_dossiers_after_triage", "message": "Gateway-eligible triage leads exist but no dossiers were produced.", "lead_ids": []})
    if counts["gateway_approved"] > 0 and counts["drafts"] == 0:
        findings.append({"severity": "blocker", "code": "zero_drafts_after_gateway", "message": "Gateway-approved leads exist but no outreach drafts were produced.", "lead_ids": []})
    if counts["drafts"] and counts["gateway_approved"] and counts["drafts"] != counts["gateway_approved"]:
        findings.append({"severity": "review", "code": "draft_gateway_count_mismatch", "message": "Draft count does not match gateway-approved count.", "lead_ids": []})

    seen: dict[str, list[str]] = {}
    for item in payload["normalized_leads"] + payload["p1_dossiers"] + payload["outreach_drafts"]:
        key = (lead_name(item).lower(), linkedin_url(item).lower())
        identity_key = "|".join(part for part in key if part)
        if identity_key:
            seen.setdefault(identity_key, []).append(lead_id(item))
    duplicate_ids = sorted({item for ids in seen.values() if len(set(ids)) > 1 for item in ids})
    if duplicate_ids:
        findings.append({"severity": "review", "code": "duplicate_candidate_identity", "message": "Possible duplicate candidate identity across P1 artifacts.", "lead_ids": first_n(duplicate_ids)})
    missing_linkedin = [lead_id(item) for item in payload["p1_dossiers"] + payload["outreach_drafts"] if not linkedin_url(item)]
    if missing_linkedin:
        findings.append({"severity": "review", "code": "missing_linkedin_url", "message": "Some dossiers or drafts are missing LinkedIn URLs.", "lead_ids": first_n(sorted(set(missing_linkedin)))})
    if counts["drafts"] > 0 and not presence["approval_preview"]:
        findings.append({"severity": "review", "code": "missing_external_action_preview", "message": "Drafts exist but no external action preview artifact was found.", "lead_ids": []})
    return findings


def evidence_findings(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    approved = [
        item for item in payload["gateway_evaluations"]
        if isinstance(item.get("gateway"), dict) and item["gateway"].get("decision") == "awaiting_outreach"
    ]
    for item in approved:
        dossier = item.get("dossier") if isinstance(item.get("dossier"), dict) else item
        urls = sorted({*evidence_urls(item), *evidence_urls(dossier)})
        domains = source_domains(urls)
        record = {
            "lead_id": lead_id(dossier),
            "name": lead_name(dossier),
            "evidence_url_count": len(urls),
            "source_domain_count": len(domains),
            "source_domains": domains,
            "linkedin_url": linkedin_url(dossier),
        }
        records.append(record)
        if not urls:
            findings.append({"severity": "review", "code": "missing_evidence_urls", "message": "Gateway-approved lead has no evidence URLs.", "lead_ids": [record["lead_id"]]})
        if len(domains) < 2:
            findings.append({"severity": "review", "code": "thin_source_diversity", "message": "Gateway-approved lead has fewer than two canonical evidence domains.", "lead_ids": [record["lead_id"]]})
        if not record["linkedin_url"]:
            findings.append({"severity": "review", "code": "missing_identity_linkedin", "message": "Gateway-approved lead is missing a verified LinkedIn identity URL.", "lead_ids": [record["lead_id"]]})
    return records, findings


def outreach_findings(payload: dict[str, Any]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    records: list[dict[str, Any]] = []
    findings: list[dict[str, Any]] = []
    normalized_texts: dict[str, list[str]] = {}
    for draft in payload["outreach_drafts"]:
        text = clean_string(draft.get("text"))
        lower = text.lower()
        words = text.split()
        urls = evidence_urls(draft)
        claims = draft.get("claims") if isinstance(draft.get("claims"), list) else []
        unsupported_claims = [
            clean_string(claim.get("text")) or f"claim_{index + 1}"
            for index, claim in enumerate(claims)
            if isinstance(claim, dict) and not clean_string(claim.get("source_url"))
        ]
        flags: list[str] = []
        if not text:
            flags.append("missing_text")
        if len(words) < 35:
            flags.append("too_short")
        if len(words) > 110:
            flags.append("too_long")
        if "abrt" not in lower and "limpid" not in lower:
            flags.append("missing_abrt_or_limpid")
        if lead_name(draft) != "unknown" and lead_name(draft).split()[0].lower() not in lower:
            flags.append("missing_recipient_name")
        if not urls:
            flags.append("missing_evidence_urls")
        if unsupported_claims:
            flags.append("unsupported_claims")
        if any(phrase in lower for phrase in GENERIC_PHRASES):
            flags.append("generic_wording")
        normalized = re.sub(r"\s+", " ", lower).strip()
        if normalized:
            normalized_texts.setdefault(normalized, []).append(lead_id(draft))
        record = {
            "lead_id": lead_id(draft),
            "name": lead_name(draft),
            "word_count": len(words),
            "evidence_url_count": len(urls),
            "claim_count": len(claims),
            "unsupported_claim_count": len(unsupported_claims),
            "flags": flags,
        }
        records.append(record)
        if flags:
            findings.append({"severity": "review", "code": "weak_outreach_draft", "message": ", ".join(flags), "lead_ids": [record["lead_id"]]})
    repeated = sorted({lead_id for lead_ids in normalized_texts.values() if len(set(lead_ids)) > 1 for lead_id in lead_ids})
    if repeated:
        findings.append({"severity": "review", "code": "repeated_outreach_template", "message": "Identical outreach draft text appears for multiple leads.", "lead_ids": first_n(repeated)})
    return records, findings


def classify_risk(run: dict[str, Any], findings: list[dict[str, Any]], counts: dict[str, int]) -> str:
    if run.get("status") == "failed":
        return "failed audit"
    blocker_codes = {str(item.get("code")) for item in findings if item.get("severity") == "blocker"}
    if blocker_codes:
        return "blocked by missing data" if any(code.startswith("missing_artifact") for code in blocker_codes) else "blocked by weak output"
    if counts["raw_leads"] == 0:
        return "blocked by missing data"
    if findings:
        return "needs review"
    return "looks healthy"


def improvement_group_code(code: str) -> str:
    if code in {"missing_evidence_urls", "thin_source_diversity"}:
        return "weak_evidence_depth"
    if code == "missing_identity_linkedin":
        return "missing_linkedin_identity"
    return code


def improvement_candidates(findings: list[dict[str, Any]], run_id: str) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    approved_missing_linkedin_ids = {
        lead
        for finding in findings
        if finding.get("code") == "missing_identity_linkedin"
        for lead in finding.get("lead_ids", [])
        if lead
    }
    for finding in findings:
        code = clean_string(finding.get("code"))
        if not code:
            continue
        if code == "missing_linkedin_url" and approved_missing_linkedin_ids:
            lead_ids = [lead for lead in finding.get("lead_ids", []) if lead]
            approved_lead_ids = [lead for lead in lead_ids if lead in approved_missing_linkedin_ids]
            other_lead_ids = [lead for lead in lead_ids if lead not in approved_missing_linkedin_ids]
            if approved_lead_ids:
                grouped.setdefault("missing_linkedin_identity", []).append({**finding, "lead_ids": approved_lead_ids})
            if other_lead_ids:
                grouped.setdefault("missing_linkedin_url", []).append({**finding, "lead_ids": other_lead_ids})
            continue
        grouped.setdefault(improvement_group_code(code), []).append(finding)
    candidates: list[dict[str, Any]] = []
    for code, items in sorted(grouped.items()):
        lead_ids = sorted({lead for item in items for lead in item.get("lead_ids", []) if lead})
        evidence = [{"run_id": run_id, "finding_code": item.get("code"), "message": item.get("message"), "lead_ids": item.get("lead_ids", [])} for item in items]
        candidates.append(_improvement_candidate_for_finding(code, items, lead_ids, evidence))
    return candidates


def _improvement_candidate_for_finding(
    code: str,
    findings: list[dict[str, Any]],
    lead_ids: list[str],
    evidence: list[dict[str, Any]],
) -> dict[str, Any]:
    affected = len(lead_ids)
    common = {
        "finding_code": code,
        "affected_lead_ids": first_n(lead_ids, 25),
        "evidence": evidence,
        "behavior_change_requires_approval": True,
    }
    if code == "weak_evidence_depth":
        return {
            **common,
            "proposal_type": "improve_eval",
            "target_component": "p1-gateway-evaluator/p1-quality-audit",
            "problem": f"Audit found weak evidence depth for {affected or len(findings)} approved P1 lead(s).",
            "proposed_change": "Require gateway-approved leads to carry at least two canonical evidence domains or explicitly mark the lead as needing more evidence before outreach drafting.",
            "risk": "A stricter evidence gate may reduce approved lead volume, but it prevents send-ready drafts from being built on thin evidence.",
            "success_check": "Run a real P1 audit on a comparable run and verify missing_evidence_urls and thin_source_diversity are absent while gateway-approved leads still have send-ready drafts.",
        }
    if code == "missing_linkedin_identity":
        return {
            **common,
            "proposal_type": "improve_worker",
            "target_component": "p1-lead-normalizer/p1-live-intel-gatherer",
            "problem": f"Audit found missing LinkedIn identity for {affected or len(findings)} P1 lead(s).",
            "proposed_change": "Tighten identity enrichment and repair so gateway-approved leads must carry an evidence-backed person LinkedIn URL or be marked as needing more evidence before outreach drafting.",
            "risk": "Stricter identity requirements may reduce approved lead volume, but they prevent outreach drafts for unverified people.",
            "success_check": "Run a real P1 audit on a comparable run and verify missing_identity_linkedin and missing_linkedin_url are absent and every approved draft has a working person LinkedIn URL.",
        }
    if code == "missing_linkedin_url":
        return {
            **common,
            "proposal_type": "improve_observability",
            "target_component": "p1-dossier-draft-identity-contract",
            "problem": f"Audit found dossier or draft records missing LinkedIn URLs for {affected or len(findings)} P1 lead(s).",
            "proposed_change": "Make dossier and draft identity completeness explicit: either carry a LinkedIn URL, or record why LinkedIn is unavailable before the lead reaches approval-ready status.",
            "risk": "This may add more review findings for incomplete leads, but it avoids confusing generic record completeness with approved-lead identity failures.",
            "success_check": "Run a real P1 audit on a comparable run and verify missing_linkedin_url is absent or explicitly accepted before approval-ready drafting.",
        }
    if code == "weak_outreach_draft":
        return {
            **common,
            "proposal_type": "improve_worker",
            "target_component": "p1-outreach-draft-writer/p1-outreach-quality-judge",
            "problem": f"Audit found weak outreach draft signals for {affected or len(findings)} P1 lead(s).",
            "proposed_change": "Tighten the outreach writer and judge so every draft has recipient-specific wording, grounded claims, ABRT/Limpid relevance, and one clear CTA.",
            "risk": "Stricter draft quality checks may block more runs at approval time, but they prevent low-quality outbound drafts.",
            "success_check": "Run a real P1 audit on a comparable run and verify weak_outreach_draft is absent and outreach quality eval still passes.",
        }
    if code.startswith("missing_artifact"):
        return {
            **common,
            "proposal_type": "improve_observability",
            "target_component": "p1-runtime-artifact-contract",
            "problem": f"Audit found missing required P1 artifact(s): {code}.",
            "proposed_change": "Make the P1 runtime fail explicitly or emit a clear diagnostic when a required audit artifact is missing after its upstream stage runs.",
            "risk": "This may surface more failed runs instead of allowing partial reports, but it makes proof-pack readiness trustworthy.",
            "success_check": "Run the real P1 audit on a comparable run and verify required artifacts are present or the run fails with a precise diagnosis.",
        }
    if code.startswith("zero_"):
        return {
            **common,
            "proposal_type": "fix_code",
            "target_component": "p1-runtime-stage-contract",
            "problem": f"Audit found a funnel stage collapse: {code}.",
            "proposed_change": "Inspect the upstream/downstream stage contract and add a real regression proof for this zero-output-after-input case.",
            "risk": "Fixing the stage contract may change worker inputs or stricter failure behavior, so it requires approval and before/after proof.",
            "success_check": "Run a comparable real P1 pipeline and verify the same stage no longer collapses after nonzero input.",
        }
    return {
        **common,
        "proposal_type": "improve_process",
        "target_component": "p1-quality-audit",
        "problem": f"Audit found repeated quality signal `{code}` for {affected or len(findings)} P1 lead(s).",
        "proposed_change": "Review the flagged leads and decide whether this should become a stricter runtime gate, worker instruction change, or eval improvement.",
        "risk": "Changing the process without human review could overfit one run, so this candidate is advisory until approved.",
        "success_check": "Run a real P1 audit on a comparable run and verify this finding is absent or explicitly accepted by the operator.",
    }


def build_quality_audit(run: dict[str, Any], summary: dict[str, Any]) -> dict[str, Any]:
    if run.get("playbook_key") != P1_PLAYBOOK_KEY:
        raise SystemExit(f"run {run.get('id')} is not a P1 operator outreach run: playbook_key={run.get('playbook_key')}")
    assert_summary_shape(summary)
    payload = collect_p1_payloads(run)
    counts = funnel_counts(payload, summary)
    presence = artifact_presence(run, summary)
    funnel = funnel_findings(payload, counts, presence)
    evidence_records, evidence = evidence_findings(payload)
    outreach_records, outreach = outreach_findings(payload)
    findings = funnel + evidence + outreach
    top_risks = [item["message"] for item in findings[:8]]
    review_focus = sorted({lead_id for item in findings for lead_id in item.get("lead_ids", []) if lead_id})
    candidates = improvement_candidates(findings, str(run.get("id") or "unknown"))
    return {
        "audit_version": "2026-06-01.p1-quality-audit-pack.v1",
        "generated_at": datetime.now(UTC).isoformat(),
        "run": {
            "id": run.get("id"),
            "status": run.get("status"),
            "playbook_key": run.get("playbook_key"),
            "goal": run.get("goal"),
            "created_at": run.get("created_at"),
            "updated_at": run.get("updated_at"),
        },
        "source_of_truth": {
            "run_endpoint": f"GET /runs/{run.get('id')}",
            "summary_endpoint": f"GET /runs/{run.get('id')}/summary",
            "runtime_tables": ["process_runs", "work_orders", "artifacts", "eval_results", "events"],
        },
        "funnel_counts": counts,
        "artifact_presence": presence,
        "eval_summary": summary.get("latest_eval_results", {}),
        "external_sync_status": summary.get("external_sync_status", {}),
        "evidence_records": evidence_records,
        "outreach_records": outreach_records,
        "findings": findings,
        "recommended_improvements": candidates,
        "risk_summary": {
            "state": classify_risk(run, findings, counts),
            "top_risks": top_risks,
            "affected_leads": first_n(review_focus, 25),
            "recommended_human_review_focus": first_n(review_focus, 25),
            "recommended_improvement_count": len(candidates),
        },
    }


def render_markdown(audit: dict[str, Any]) -> str:
    counts = audit["funnel_counts"]
    risk = audit["risk_summary"]
    lines = [
        "# P1 Quality Audit Pack",
        "",
        f"Generated at: `{audit['generated_at']}`",
        f"Run ID: `{audit['run']['id']}`",
        f"Run status: `{audit['run']['status']}`",
        f"Risk state: **{risk['state']}**",
        "",
        "## Source Of Truth",
        "",
        f"- `{audit['source_of_truth']['run_endpoint']}`",
        f"- `{audit['source_of_truth']['summary_endpoint']}`",
        "- Runtime data: `process_runs`, `work_orders`, `artifacts`, `eval_results`, `events`",
        "",
        "## Funnel Counts",
        "",
        "| Stage | Count |",
        "| --- | ---: |",
    ]
    for key in (
        "raw_leads",
        "normalized_leads",
        "rejected_leads",
        "triage_total",
        "triage_qualified",
        "dossiers",
        "gateway_total",
        "gateway_approved",
        "drafts",
        "sheet_written",
        "data_lake_written",
        "outreach_master_written",
    ):
        lines.append(f"| `{key}` | {counts[key]} |")
    lines.extend(["", "## Findings", ""])
    if audit["findings"]:
        lines.extend(["| Severity | Code | Message | Leads |", "| --- | --- | --- | --- |"])
        for item in audit["findings"]:
            leads = ", ".join(item.get("lead_ids") or [])
            lines.append(f"| {item.get('severity')} | `{item.get('code')}` | {item.get('message')} | {leads} |")
    else:
        lines.append("No audit findings were produced.")
    lines.extend(["", "## Evidence Signals", ""])
    if audit["evidence_records"]:
        lines.extend(["| Lead | Evidence URLs | Source Domains | LinkedIn |", "| --- | ---: | ---: | --- |"])
        for item in audit["evidence_records"]:
            lines.append(f"| {item['name']} (`{item['lead_id']}`) | {item['evidence_url_count']} | {item['source_domain_count']} | {item['linkedin_url'] or 'missing'} |")
    else:
        lines.append("No gateway-approved evidence records were available for inspection.")
    lines.extend(["", "## Outreach Signals", ""])
    if audit["outreach_records"]:
        lines.extend(["| Lead | Words | Evidence URLs | Unsupported Claims | Flags |", "| --- | ---: | ---: | ---: | --- |"])
        for item in audit["outreach_records"]:
            lines.append(f"| {item['name']} (`{item['lead_id']}`) | {item['word_count']} | {item['evidence_url_count']} | {item['unsupported_claim_count']} | {', '.join(item['flags']) or 'none'} |")
    else:
        lines.append("No outreach drafts were available for inspection.")
    lines.extend(["", "## Recommended Improvements", ""])
    improvements = audit.get("recommended_improvements", []) if isinstance(audit.get("recommended_improvements"), list) else []
    if improvements:
        lines.extend(["| Type | Target | Problem | Success Check |", "| --- | --- | --- | --- |"])
        for item in improvements:
            lines.append(
                f"| `{item.get('proposal_type')}` | `{item.get('target_component')}` | {item.get('problem')} | {item.get('success_check')} |"
            )
    else:
        lines.append("No improvement candidates were generated.")
    lines.extend(["", "## Human Review Focus", ""])
    if risk["recommended_human_review_focus"]:
        for lead in risk["recommended_human_review_focus"]:
            lines.append(f"- `{lead}`")
    else:
        lines.append("No specific lead IDs were flagged.")
    lines.extend(["", "## Limits", "", "This audit surfaces reproducible quality signals. It does not replace Nikita's human production-readiness judgment."])
    return "\n".join(lines) + "\n"


def write_outputs(audit: dict[str, Any], json_output: Path, markdown_output: Path) -> None:
    json_output.parent.mkdir(parents=True, exist_ok=True)
    markdown_output.parent.mkdir(parents=True, exist_ok=True)
    json_output.write_text(json.dumps(audit, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    markdown_output.write_text(render_markdown(audit), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Build a read-only quality audit pack for one real P1 run.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--run-id", required=True, help="Required real P1 run id. The command never chooses an example run.")
    parser.add_argument("--json-output", default=str(DEFAULT_JSON_OUTPUT))
    parser.add_argument("--markdown-output", default=str(DEFAULT_MARKDOWN_OUTPUT))
    args = parser.parse_args()

    require_health(args.base_url)
    require_capabilities(args.base_url)
    run = request_json(f"{args.base_url}/runs/{args.run_id}")
    summary = request_json(f"{args.base_url}/runs/{args.run_id}/summary")
    audit = build_quality_audit(run, summary)
    write_outputs(audit, Path(args.json_output), Path(args.markdown_output))
    print(json.dumps({"run_id": args.run_id, "risk_state": audit["risk_summary"]["state"], "json_output": args.json_output, "markdown_output": args.markdown_output}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
