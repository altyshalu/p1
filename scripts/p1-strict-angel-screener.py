#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
from datetime import date
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.request


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MODEL = "gemini-2.5-flash"
GATEWAY_STATUS = "gateway_eligible"
REQUIRED_GATES = (
    "b2c_or_plg_product_experience",
    "product_leadership",
    "verified_angel_or_check_writer",
    "geography_language_fit",
)
BLOCKING_GATES = ("excluded_industry", "excluded_profile_type")
OUTPUT_FIELDS = [
    "Date Added",
    "Name",
    "LinkedIn",
    "City",
    "Country",
    "Headline",
    "P1 Score",
    "P1 Status",
    "Verdict",
    "P1 Reasoning",
]


STRICT_P1_PROMPT = """
You are the P1 Triage Agent for Limpid/ABRT. Score this real operator/angel lead.

Lead:
{lead_json}

Rules:
- Keep only people who have BOTH real B2C/consumer/marketplace/gaming/viral fintech/PLG operator experience AND personal angel/check-writer/scout/micro-fund evidence.
- Geography mode: {geography_mode}.
- Reject heavy enterprise-only B2B SaaS, consulting-only, investor-only/VC-only without operator history, advisor-only, corporate finance, commercial banking, biotech, defense, medical equipment, heavy industry, and real estate.
- In Europe mode, also reject Cyprus and US-only/non-Europe profiles. In worldwide mode, geography_language_fit may pass for any geography except Cyprus.
- b2c_plg_dna_score 0-45: 35-45 for mass-market consumer apps, gaming, viral fintech, marketplaces, social, travel, or consumer internet; 25-35 for PLG/SMB self-serve or bottom-up products like Wise, Slack, Dropbox, Box, Figma, Notion; 0 for enterprise/sales-led/consulting.
- product_leadership_score is deprecated; return 0.
- verified_angel_score 0-35: 25-35 for active angel/check-writer/scout/Atomico angel allocation/micro-fund/personal portfolio; 10-20 only for capital potential; 0 for no personal investing evidence.
- liquidity_ecosystem_score is deprecated; return 0.
- systematic_fit_score 0-20 for explicit data/AI/ML/quant/metrics/growth systems or analytical product/growth background.
- geography_language_score is deprecated; return 0.
- hard_gates.b2c_or_plg_product_experience true only when real B2C/PLG product experience exists.
- hard_gates.product_leadership true for founder/CEO/CPO/CTO/product/growth leadership ownership.
- hard_gates.verified_angel_or_check_writer true only for personal angel/check-writing/scout/micro-fund/Atomico angel evidence.
- hard_gates.geography_language_fit true according to the selected geography mode.
- hard_gates.excluded_industry true for excluded industries above.
- hard_gates.excluded_profile_type true for investor-only/VC-only/advisor-only/mentor-only without operator history.
- evidence_urls must include the source URLs supporting the score when available.

Return JSON only with keys: b2c_plg_dna_score, product_leadership_score, verified_angel_score, liquidity_ecosystem_score, systematic_fit_score, geography_language_score, hard_gates, evidence_urls, reasoning.
"""


def load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value)
    if not path.exists():
        raise SystemExit(f"env file does not exist: {path}")
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def read_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def load_candidates(path_value: str) -> list[dict[str, Any]]:
    path = Path(path_value)
    if not path.is_absolute():
        path = ROOT / path
    if path.suffix.lower() == ".json":
        payload = read_json(path)
        if isinstance(payload, dict):
            payload = payload.get("candidates")
        if not isinstance(payload, list):
            raise SystemExit("candidate JSON must be a list or an object with candidates=list")
        return [normalize_candidate(item) for item in payload if isinstance(item, dict)]
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8", newline="") as handle:
        return [normalize_candidate(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def normalize_candidate(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence")
    if isinstance(evidence, str):
        evidence_values = [part.strip() for part in re.split(r"\s*\|\s*|\n", evidence) if part.strip()]
    elif isinstance(evidence, list):
        evidence_values = [str(part).strip() for part in evidence if str(part).strip()]
    else:
        evidence_values = []
    return {
        "name": text_value(item, "name", "Name"),
        "linkedin_url": text_value(item, "linkedin_url", "LinkedIn", "LinkedIn URL"),
        "city": text_value(item, "city", "City"),
        "country": text_value(item, "country", "Country"),
        "headline": text_value(item, "headline", "Headline"),
        "evidence": evidence_values,
    }


def text_value(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return str(value).strip()
    return ""


def load_seen_names(paths: list[str], csv_urls: list[str]) -> set[str]:
    seen: set[str] = set()
    for path_value in paths:
        path = Path(path_value)
        if not path.exists():
            continue
        if path.suffix.lower() in {".csv", ".tsv"}:
            delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
            with path.open(encoding="utf-8", newline="") as handle:
                for row in csv.DictReader(handle, delimiter=delimiter):
                    name = text_value(row, "Name", "name")
                    if name:
                        seen.add(clean_key(name))
        else:
            seen.update(clean_key(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
    for url in csv_urls:
        data = fetch_url_text(url)
        for row in csv.DictReader(data.splitlines()):
            name = text_value(row, "Name", "name")
            if name:
                seen.add(clean_key(name))
    return seen


def fetch_url_text(url: str) -> str:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(request, timeout=45) as response:
        return response.read().decode("utf-8-sig")


def clean_key(value: str) -> str:
    return re.sub(r"\s+", " ", value.strip().lower())


def gemini_json(api_key: str, model: str, prompt: str) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={api_key}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "maxOutputTokens": 4096},
    }
    attempts = [
        body,
        {
            **body,
            "contents": [{"parts": [{"text": f"{prompt}\n\nReturn one complete valid JSON object only. Do not use markdown fences."}]}],
        },
    ]
    last_text = ""
    for payload in attempts:
        request = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=75) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw["candidates"][0]["content"]["parts"][0]["text"].strip()
        text = text.replace("```json", "").replace("```", "").strip()
        last_text = text
        try:
            parsed = json.loads(text)
        except json.JSONDecodeError:
            continue
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError(f"Gemini returned invalid JSON: {last_text[:300]}")


def score_candidate(candidate: dict[str, Any], api_key: str, model: str) -> dict[str, Any]:
    lead = {
        "name": candidate["name"],
        "headline": candidate["headline"],
        "location": ", ".join(part for part in [candidate["city"], candidate["country"]] if part),
        "linkedin_url": candidate["linkedin_url"],
        "source_url": candidate["linkedin_url"],
        "source": "p1_strict_angel_screener",
        "evidence": candidate["evidence"],
    }
    geography_mode = os.environ.get("P1_ANGEL_GEOGRAPHY_MODE", "europe").strip().lower()
    if geography_mode not in {"europe", "worldwide"}:
        geography_mode = "europe"
    response = gemini_json(
        api_key,
        model,
        STRICT_P1_PROMPT.format(lead_json=json.dumps(lead, ensure_ascii=False), geography_mode=geography_mode),
    )
    return normalize_triage(response)


def normalize_triage(response: dict[str, Any]) -> dict[str, Any]:
    b2c_score = bounded_int(response.get("b2c_plg_dna_score", response.get("b2c_dna_score")), 0, 45)
    angel_score = bounded_int(response.get("verified_angel_score", response.get("investor_score")), 0, 35)
    systematic_score = bounded_int(response.get("systematic_fit_score", response.get("systematic_score")), 0, 20)
    hard_gates = response.get("hard_gates") if isinstance(response.get("hard_gates"), dict) else {}
    gates = {
        "b2c_or_plg_product_experience": bool_gate(hard_gates.get("b2c_or_plg_product_experience")),
        "product_leadership": bool_gate(hard_gates.get("product_leadership")),
        "verified_angel_or_check_writer": bool_gate(hard_gates.get("verified_angel_or_check_writer")),
        "geography_language_fit": bool_gate(hard_gates.get("geography_language_fit")),
        "excluded_industry": bool_gate(hard_gates.get("excluded_industry") or response.get("is_blacklist")),
        "excluded_profile_type": bool_gate(hard_gates.get("excluded_profile_type")),
    }
    total = b2c_score + angel_score + systematic_score
    missing = [gate for gate in REQUIRED_GATES if gates.get(gate) is not True]
    blocking = [gate for gate in BLOCKING_GATES if gates.get(gate) is True]
    if blocking:
        status = "reject"
    elif missing:
        status = "needs_enrichment" if total >= 60 else "reject"
    elif total >= 60:
        status = GATEWAY_STATUS
    elif total >= 45:
        status = "data_lake_only"
    else:
        status = "reject"
    return {
        **response,
        "b2c_plg_dna_score": b2c_score,
        "product_leadership_score": 0,
        "verified_angel_score": angel_score,
        "liquidity_ecosystem_score": 0,
        "systematic_fit_score": systematic_score,
        "geography_language_score": 0,
        "hard_gates": gates,
        "total_score": total,
        "status": status,
        "qualified": status == GATEWAY_STATUS,
        "missing_required_gates": missing,
        "blocking_gates": blocking,
        "reject_reason": reject_reason(status, total, missing, blocking),
    }


def bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))


def bool_gate(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "pass", "passed"}
    return False


def reject_reason(status: str, total: int, missing: list[str], blocking: list[str]) -> str:
    if status == GATEWAY_STATUS:
        return ""
    if blocking:
        return f"blocking_gates:{','.join(blocking)}"
    if missing:
        return f"missing_required_gates:{','.join(missing)}"
    return f"score_below_gateway_threshold:{total}"


def write_outputs(rows: list[dict[str, Any]], output_path: Path, audit_path: Path, date_added: str, limit: int) -> None:
    approved = [row for row in rows if row["triage"].get("qualified") is True]
    approved.sort(key=lambda row: (int(row["triage"].get("total_score") or 0), row["candidate"]["name"]), reverse=True)
    output_rows = approved[:limit]
    with output_path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=OUTPUT_FIELDS, delimiter="\t", lineterminator="\n")
        writer.writeheader()
        for row in output_rows:
            candidate = row["candidate"]
            triage = row["triage"]
            writer.writerow(
                {
                    "Date Added": date_added,
                    "Name": candidate["name"],
                    "LinkedIn": candidate["linkedin_url"],
                    "City": candidate["city"],
                    "Country": candidate["country"],
                    "Headline": candidate["headline"],
                    "P1 Score": triage["total_score"],
                    "P1 Status": triage["status"],
                    "Verdict": "approve",
                    "P1 Reasoning": re.sub(r"\s+", " ", str(triage.get("reasoning", ""))).strip()[:600],
                }
            )
    audit_path.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Strict P1 screener for Europe angel candidates.")
    parser.add_argument("--candidates", required=True, help="JSON/CSV/TSV candidate file.")
    parser.add_argument("--output", default="/tmp/p1_strict_approved_angels.tsv")
    parser.add_argument("--audit-output", default="/tmp/p1_strict_angel_audit.json")
    parser.add_argument("--env-file", default=".env")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=50)
    parser.add_argument("--date-added", default=date.today().isoformat())
    parser.add_argument("--seen-file", action="append", default=[], help="Text/CSV/TSV file with existing names to skip.")
    parser.add_argument("--seen-csv-url", action="append", default=[], help="Google Sheets CSV export URL with existing names to skip.")
    parser.add_argument("--sleep-seconds", type=float, default=0.1)
    args = parser.parse_args()

    load_env_file(args.env_file)
    api_key = os.environ.get("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise SystemExit("GEMINI_API_KEY is required")

    candidates = load_candidates(args.candidates)
    seen_names = load_seen_names(args.seen_file, args.seen_csv_url)
    deduped: list[dict[str, Any]] = []
    local_seen: set[str] = set()
    for candidate in candidates:
        name_key = clean_key(candidate["name"])
        if not candidate["name"] or name_key in seen_names or name_key in local_seen:
            continue
        local_seen.add(name_key)
        deduped.append(candidate)

    rows: list[dict[str, Any]] = []
    for index, candidate in enumerate(deduped, start=1):
        try:
            triage = score_candidate(candidate, api_key, args.model)
        except Exception as exc:
            triage = {
                "total_score": 0,
                "status": "error",
                "qualified": False,
                "reject_reason": str(exc)[:300],
                "reasoning": str(exc)[:300],
                "missing_required_gates": [],
                "blocking_gates": [],
            }
        rows.append({"candidate": candidate, "triage": triage})
        print(
            f"{index}/{len(deduped)} {candidate['name']} {triage.get('total_score')} {triage.get('status')} {triage.get('reject_reason', '')}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(args.sleep_seconds)

    output_path = Path(args.output)
    audit_path = Path(args.audit_output)
    write_outputs(rows, output_path, audit_path, args.date_added, args.limit)
    approved_count = sum(1 for row in rows if row["triage"].get("qualified") is True)
    print(json.dumps({"candidates": len(deduped), "approved": approved_count, "output": str(output_path), "audit_output": str(audit_path)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
