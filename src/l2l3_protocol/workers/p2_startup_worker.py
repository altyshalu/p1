from __future__ import annotations

import hashlib
import json
import os
import re
import sys
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urlparse
from urllib.request import Request, urlopen

from l2l3_protocol.workers.p1_operator_worker import _google_access_token, _request_json


P2_DEFAULT_SOURCE_TABS = ["From Database", "New / External"]
P2_DEFAULT_OUTPUT_TAB = "Suitable Startups"

P2_STARTUP_HEADERS = [
    "Company Name",
    "Website URL",
    "Founder LinkedIn URL(s)",
    "Founder LinkedIn URL 2",
    "Founder LinkedIn URL 3",
    "Founder LinkedIn URL 4",
    "Country of Incorporation",
    "Startup Stage",
    "Pitch Deck Link",
    "ARR",
    "MoM Growth",
    "Burn",
    "CAC",
    "Additional Decision-Useful Info",
    "Ohio Fit Score",
    "Synth ARR",
    "Synth MRR",
    "Synth Revenue Growth %",
    "Synth Churn Rate %",
    "Synth Paid CAC",
    "Synth Contracts Signed",
    "Synth Contracts Pipeline",
    "Synth CAC Payback (mo)",
    "Synth Retention %",
    "Synth User Growth %",
    "Synth LTV/CAC",
    "Synth DAU",
    "Synth MAU",
    "Synth AI Approach",
    "Synth Business Model",
    "Data Type",
    "Cohort Basis",
    "Direction",
    "Judge Tag",
    "Judge Reason",
    "Human Review Notes",
    "ICP Version",
    "Source Tab",
    "Website Verification Status",
    "Website Verification Note",
    "Website Final URL",
]

LINKEDIN_RE = re.compile(r"https?://(?:[a-z]{2,3}\.)?linkedin\.com/[^\s,;|)]+", re.IGNORECASE)
URL_RE = re.compile(r"https?://[^\s,;|)]+", re.IGNORECASE)

HEADER_ALIASES = {
    "company": "Company Name",
    "company name": "Company Name",
    "startup": "Company Name",
    "startup name": "Company Name",
    "name": "Company Name",
    "website": "Website URL",
    "website url": "Website URL",
    "company website": "Website URL",
    "url": "Website URL",
    "founder linkedin": "Founder LinkedIn URL(s)",
    "founder linkedin url": "Founder LinkedIn URL(s)",
    "founder linkedin urls": "Founder LinkedIn URL(s)",
    "linkedin": "Founder LinkedIn URL(s)",
    "founders linkedin": "Founder LinkedIn URL(s)",
    "country": "Country of Incorporation",
    "country of incorporation": "Country of Incorporation",
    "stage": "Startup Stage",
    "startup stage": "Startup Stage",
    "pitch deck": "Pitch Deck Link",
    "pitch deck link": "Pitch Deck Link",
    "description": "Additional Decision-Useful Info",
    "additional decision-useful info": "Additional Decision-Useful Info",
    "info": "Additional Decision-Useful Info",
    "ohio fit score": "Ohio Fit Score",
    "score": "Ohio Fit Score",
    "direction": "Direction",
    "sector": "Direction",
    "category": "Direction",
    "judge tag": "Judge Tag",
    "judge reason": "Judge Reason",
    "source tab": "Source Tab",
}

SECTOR_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("AI / Generative Tech", (" generative", " genai", " llm", " ai ", " artificial intelligence", "copilot", "agentic", "machine learning")),
    ("Cybersecurity", ("cyber", "security", "soc ", "zero trust", "identity", "fraud")),
    ("FinTech", ("fintech", "payment", "banking", "lending", "wealth", "insurance", "crypto", "defi")),
    ("HealthTech", ("health", "clinical", "patient", "medtech", "biotech", "pharma", "diagnostic")),
    ("EdTech", ("education", "edtech", "learning", "student", "school", "university", "tutor")),
    ("HRTech", ("hr ", "hiring", "recruit", "talent", "workforce", "employee")),
    ("PropTech", ("real estate", "property", "proptech", "construction", "facility")),
    ("Climate", ("climate", "carbon", "energy", "battery", "solar", "sustainability")),
    ("DeepTech", ("robotics", "hardware", "semiconductor", "quantum", "aerospace", "materials", "sensors")),
    ("Marketplace", ("marketplace", "platform for", "connects buyers", "buyers and sellers")),
    ("Consumer", ("consumer", "creator", "social", "gaming", "wellness", "fitness")),
    ("Enterprise SaaS", ("saas", "enterprise", "b2b", "workflow", "crm", "automation", "analytics", "data platform")),
]

BLOCKED_SITE_HINTS = (
    "linkedin.com",
    "crunchbase.com",
    "pitchbook.com",
    "wellfound.com",
    "angellist.com",
    "medium.com",
    "substack.com",
    "techcrunch.com",
    "forbes.com",
    "jobs.",
    "greenhouse.io",
    "lever.co",
    "workable.com",
)


class P2WorkerInputError(ValueError):
    pass


@dataclass(frozen=True)
class WebsiteCheck:
    status: str
    note: str
    final_url: str
    website_url: str
    corrected: bool = False


def _inputs(work_order: dict[str, Any]) -> dict[str, Any]:
    inputs = work_order.get("inputs", {})
    if not isinstance(inputs, dict):
        raise P2WorkerInputError("P2 worker inputs must be an object")
    return inputs


def _text(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _canonical_header(value: Any) -> str:
    raw = _text(value)
    key = raw.lower().strip()
    return HEADER_ALIASES.get(key, raw)


def _unique_headers(headers: list[Any]) -> tuple[list[str], list[str]]:
    seen: dict[str, int] = {}
    out: list[str] = []
    drift: list[str] = []
    for idx, header in enumerate(headers):
        name = _canonical_header(header) or f"Column {idx + 1}"
        seen[name] = seen.get(name, 0) + 1
        if seen[name] > 1:
            drift.append(f"duplicate header '{name}' at column {idx + 1}")
            name = f"{name} {seen[name]}"
        out.append(name)
    return out, drift


def _sheet_values_to_rows(tab: str, values: list[list[Any]]) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if not values:
        return [], {"tab": tab, "row_count": 0, "drift": ["empty tab"]}
    headers, drift = _unique_headers(values[0])
    rows: list[dict[str, Any]] = []
    for row_index, values_row in enumerate(values[1:], start=2):
        if len(values_row) != len(headers):
            drift.append(f"row {row_index} has {len(values_row)} cells, expected {len(headers)}")
        row = {header: values_row[index] if index < len(values_row) else "" for index, header in enumerate(headers)}
        row["_source_tab"] = tab
        row["_sheet_row_number"] = row_index
        rows.append(row)
    return rows, {"tab": tab, "headers": headers, "row_count": len(rows), "drift": drift}


def _rows_from_inline_tab(tab: str, tab_payload: Any) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    if isinstance(tab_payload, dict):
        headers = tab_payload.get("headers")
        rows = tab_payload.get("rows", [])
        if headers:
            values = [headers, *rows]
            return _sheet_values_to_rows(tab, values)
        if isinstance(rows, list) and all(isinstance(row, dict) for row in rows):
            result = []
            for index, row in enumerate(rows, start=2):
                result.append({**row, "_source_tab": tab, "_sheet_row_number": row.get("_sheet_row_number", index)})
            return result, {"tab": tab, "headers": sorted({key for row in result for key in row}), "row_count": len(result), "drift": []}
    if isinstance(tab_payload, list) and tab_payload and all(isinstance(row, dict) for row in tab_payload):
        result = []
        for index, row in enumerate(tab_payload, start=2):
            result.append({**row, "_source_tab": tab, "_sheet_row_number": row.get("_sheet_row_number", index)})
        return result, {"tab": tab, "headers": sorted({key for row in result for key in row}), "row_count": len(result), "drift": []}
    if isinstance(tab_payload, list):
        return _sheet_values_to_rows(tab, tab_payload)
    raise P2WorkerInputError(f"unsupported inline sheet payload for tab {tab!r}")


def _read_google_sheet_values(spreadsheet_id: str, tab_name: str, token: str) -> list[list[Any]]:
    encoded_range = quote(f"{tab_name}!A:ZZ", safe="")
    url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}"
    response = _request_json("GET", url, token)
    values = response.get("values", [])
    if not isinstance(values, list):
        raise P2WorkerInputError(f"Google Sheets tab {tab_name!r} returned invalid values")
    return values


def _google_values_update(spreadsheet_id: str, tab_name: str, values: list[list[Any]], token: str) -> dict[str, Any]:
    encoded_range = quote(f"{tab_name}!A1", safe="")
    clear_range = quote(f"{tab_name}!A:ZZ", safe="")
    _ensure_google_sheet_tab(spreadsheet_id, tab_name, token)
    _request_json("POST", f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{clear_range}:clear", token, {})
    return _request_json(
        "PUT",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}?valueInputOption=RAW",
        token,
        {"values": values},
    )


def _ensure_google_sheet_tab(spreadsheet_id: str, tab_name: str, token: str) -> None:
    metadata = _request_json("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?fields=sheets.properties", token)
    sheets = metadata.get("sheets", [])
    for sheet in sheets if isinstance(sheets, list) else []:
        properties = sheet.get("properties", {}) if isinstance(sheet, dict) else {}
        if properties.get("title") == tab_name:
            return
    _request_json(
        "POST",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
        token,
        {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    )


def read_sheets(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    inputs = _inputs(work_order)
    source_tabs = inputs.get("source_tabs") or P2_DEFAULT_SOURCE_TABS
    if not isinstance(source_tabs, list) or not source_tabs:
        raise P2WorkerInputError("source_tabs must be a non-empty list")
    raw_rows: list[dict[str, Any]] = []
    metadata: list[dict[str, Any]] = []
    inline = inputs.get("sheet_rows_by_tab")
    if isinstance(inline, dict):
        for tab in source_tabs:
            rows, meta = _rows_from_inline_tab(str(tab), inline.get(tab, []))
            raw_rows.extend(rows)
            metadata.append(meta)
    else:
        spreadsheet_id = _text(inputs.get("spreadsheet_id") or os.environ.get("P2_GOOGLE_SHEET_ID"))
        if not spreadsheet_id:
            raise P2WorkerInputError("spreadsheet_id is required when sheet_rows_by_tab is not provided")
        sa_path = _text(inputs.get("google_service_account_path") or os.environ.get("GOOGLE_SA_PATH"))
        token = _google_access_token(sa_path)
        for tab in source_tabs:
            values = _read_google_sheet_values(spreadsheet_id, str(tab), token)
            rows, meta = _sheet_values_to_rows(str(tab), values)
            raw_rows.extend(rows)
            metadata.append(meta)
    limit = int(inputs.get("limit") or 1000)
    raw_rows = raw_rows[: max(0, limit)]
    return {
        "raw_startup_rows": raw_rows,
        "sheet_metadata": metadata,
        "drift_report": [issue for meta in metadata for issue in meta.get("drift", [])],
    }


def _clean_url(value: Any) -> str:
    raw = _text(value)
    if not raw or raw.upper() == "[TBC]":
        return ""
    match = URL_RE.search(raw)
    if match:
        raw = match.group(0)
    if raw and not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw.rstrip(".,; )]")


def _company_name(row: dict[str, Any]) -> str:
    for key in ("Company Name", "Company", "Startup", "Startup Name", "Name"):
        value = _lookup(row, key)
        if _text(value):
            return _text(value)
    return ""


def _lookup(row: dict[str, Any], name: str) -> Any:
    if name in row:
        return row.get(name)
    lower = name.lower()
    for key, value in row.items():
        if str(key).lower() == lower:
            return value
    return ""


def _field(row: dict[str, Any], canonical: str) -> str:
    value = _lookup(row, canonical)
    if _text(value):
        return _text(value)
    for key, target in HEADER_ALIASES.items():
        value = _lookup(row, key)
        if target == canonical and _text(value):
            return _text(value)
    return ""


def _is_placeholder(row: dict[str, Any]) -> bool:
    joined = " ".join(_text(value).lower() for key, value in row.items() if not key.startswith("_")).strip()
    if not joined:
        return True
    return joined in {"n/a", "na", "none", "tbc", "[tbc]", "todo"} or "placeholder" in joined


def normalize_startups(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    rows = _inputs(work_order).get("raw_startup_rows", [])
    if not isinstance(rows, list):
        raise P2WorkerInputError("raw_startup_rows must be a list")
    normalized: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            rejected.append({"reason": "row is not an object", "row": row})
            continue
        if _is_placeholder(row):
            rejected.append({"reason": "empty or placeholder row", "row": row})
            continue
        name = _company_name(row)
        website = _clean_url(_field(row, "Website URL"))
        if not name and not website:
            rejected.append({"reason": "missing company name and website", "row": row})
            continue
        item = {header: _text(row.get(header)) for header in P2_STARTUP_HEADERS}
        for original_key, canonical in HEADER_ALIASES.items():
            if canonical in item and not item[canonical] and _text(row.get(original_key)):
                item[canonical] = _text(row.get(original_key))
        item["Company Name"] = name or website
        item["Website URL"] = website or _field(row, "Website URL")
        item["Founder LinkedIn URL(s)"] = _field(row, "Founder LinkedIn URL(s)") or item.get("Founder LinkedIn URL(s)", "")
        item["Country of Incorporation"] = _field(row, "Country of Incorporation") or item.get("Country of Incorporation", "")
        item["Startup Stage"] = _field(row, "Startup Stage") or item.get("Startup Stage", "")
        item["Additional Decision-Useful Info"] = _field(row, "Additional Decision-Useful Info") or item.get("Additional Decision-Useful Info", "")
        item["Source Tab"] = _text(row.get("Source Tab") or row.get("_source_tab"))
        item["_sheet_row_number"] = row.get("_sheet_row_number")
        item["_source_tab"] = row.get("_source_tab") or item["Source Tab"]
        normalized.append(item)
    return {"normalized_startups": normalized, "rejected_startups": rejected}


def _extract_linkedin_urls(*values: Any) -> list[str]:
    links: list[str] = []
    seen: set[str] = set()
    for value in values:
        for match in LINKEDIN_RE.findall(_text(value)):
            cleaned = match.split("?")[0].rstrip("/").rstrip(".,;")
            if not cleaned.startswith("https://"):
                cleaned = re.sub(r"^http://", "https://", cleaned)
            key = cleaned.lower()
            if key not in seen:
                seen.add(key)
                links.append(cleaned)
    return links


def resolve_founder_links(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    startups = _startup_list(_inputs(work_order), "normalized_startups")
    resolved = []
    max_links = 4
    for startup in startups:
        row = dict(startup)
        links = _extract_linkedin_urls(
            row.get("Founder LinkedIn URL(s)"),
            row.get("Founder LinkedIn URL 2"),
            row.get("Founder LinkedIn URL 3"),
            row.get("Founder LinkedIn URL 4"),
        )
        max_links = max(max_links, len(links))
        for index, link in enumerate(links, start=1):
            key = "Founder LinkedIn URL(s)" if index == 1 else f"Founder LinkedIn URL {index}"
            row[key] = link
        for index in range(len(links) + 1, max(5, max_links + 1)):
            key = "Founder LinkedIn URL(s)" if index == 1 else f"Founder LinkedIn URL {index}"
            row.setdefault(key, "")
        row["Founder LinkedIn Count"] = len(links)
        resolved.append(row)
    return {"founder_links_resolved": resolved}


def _startup_list(inputs: dict[str, Any], key: str) -> list[dict[str, Any]]:
    value = inputs.get(key)
    if value is None:
        for fallback in (
            "normalized_startups",
            "founder_links_resolved",
            "website_verification",
            "sector_classification",
            "icp_scores",
            "synthetic_benchmarks",
            "judge_results",
            "suitable_startups",
        ):
            value = inputs.get(fallback)
            if value is not None:
                break
    if not isinstance(value, list):
        raise P2WorkerInputError(f"{key} must be a list")
    return [dict(item) for item in value if isinstance(item, dict)]


def _url_domain(url: str) -> str:
    parsed = urlparse(_clean_url(url))
    return parsed.netloc.lower().removeprefix("www.")


def _website_check_from_override(startup: dict[str, Any], overrides: dict[str, Any]) -> WebsiteCheck | None:
    name_key = _normalize_name_key(startup.get("Company Name"))
    website_key = _normalize_url_key(startup.get("Website URL"))
    override = overrides.get(name_key) or overrides.get(website_key) or overrides.get(_text(startup.get("Company Name")))
    if not isinstance(override, dict):
        return None
    website = _clean_url(override.get("website_url") or override.get("Website URL") or startup.get("Website URL"))
    final_url = _clean_url(override.get("final_url") or override.get("Website Final URL") or website)
    status = _text(override.get("status") or override.get("Website Verification Status") or "Verified")
    note = _text(override.get("note") or override.get("Website Verification Note") or "Website verified by override.")
    return WebsiteCheck(status=status, note=note, final_url=final_url, website_url=website, corrected=website != _clean_url(startup.get("Website URL")))


def _static_website_check(startup: dict[str, Any]) -> WebsiteCheck:
    website = _clean_url(startup.get("Website URL"))
    if not website:
        return WebsiteCheck("Needs manual verification", "No company website found; marked [TBC].", "", "[TBC]")
    domain = _url_domain(website)
    if any(hint in domain or hint in website.lower() for hint in BLOCKED_SITE_HINTS):
        return WebsiteCheck("Needs manual verification", f"URL appears to be a non-official company page ({domain}); manual repair required.", website, "[TBC]")
    if domain.endswith((".pdf", ".doc", ".docx")) or "/jobs/" in website.lower() or "/careers/" in website.lower():
        return WebsiteCheck("Needs manual verification", "URL is not a stable official company homepage; manual repair required.", website, "[TBC]")
    return WebsiteCheck("Verified", "URL format and domain look like an official company website.", website, website)


def _live_website_check(startup: dict[str, Any]) -> WebsiteCheck:
    static = _static_website_check(startup)
    if static.status != "Verified":
        return static
    request = Request(static.website_url, headers={"User-Agent": "Mozilla/5.0 (compatible; ABRT-P2-URLVerifier/1.0)"})
    try:
        with urlopen(request, timeout=12) as response:
            status = int(getattr(response, "status", 0) or response.getcode())
            final_url = response.geturl()
            body = response.read(150_000).decode("utf-8", errors="ignore").lower()
    except HTTPError as exc:
        return WebsiteCheck("Needs manual verification", f"Website returned HTTP {exc.code}; manual verification required.", static.website_url, "[TBC]")
    except (URLError, TimeoutError, OSError) as exc:
        return WebsiteCheck("Needs manual verification", f"Website request failed: {type(exc).__name__}; manual verification required.", static.website_url, "[TBC]")
    if status >= 400:
        return WebsiteCheck("Needs manual verification", f"Website returned HTTP {status}; manual verification required.", final_url, "[TBC]")
    if any(term in body for term in ("domain for sale", "buy this domain", "parked free", "this domain is parked")):
        return WebsiteCheck("Needs manual verification", "Website appears parked; manual repair required.", final_url, "[TBC]")
    return WebsiteCheck("Verified", f"Website returned HTTP {status}.", final_url, static.website_url, corrected=_clean_url(final_url) != _clean_url(static.website_url))


def verify_websites(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    inputs = _inputs(work_order)
    startups = _startup_list(inputs, "founder_links_resolved")
    overrides = inputs.get("website_verification_overrides") or {}
    if not isinstance(overrides, dict):
        overrides = {}
    live = bool(inputs.get("verify_urls_live", False))
    verified: list[dict[str, Any]] = []
    corrected = 0
    tbc = 0
    for startup in startups:
        row = dict(startup)
        check = _website_check_from_override(row, overrides)
        if check is None:
            check = _live_website_check(row) if live else _static_website_check(row)
        row["Website URL"] = check.website_url
        row["Website Verification Status"] = check.status
        row["Website Verification Note"] = check.note
        row["Website Final URL"] = check.final_url
        corrected += int(check.corrected)
        tbc += int(check.status != "Verified" or check.website_url == "[TBC]")
        verified.append(row)
    return {
        "website_verification": verified,
        "verification_summary": {
            "input_count": len(startups),
            "verified_count": sum(1 for row in verified if row.get("Website Verification Status") == "Verified"),
            "corrected_urls": corrected,
            "tbc_urls": tbc,
        },
    }


def classify_sectors(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    startups = _startup_list(_inputs(work_order), "website_verification")
    classified: list[dict[str, Any]] = []
    counts: dict[str, int] = {}
    for startup in startups:
        row = dict(startup)
        direction = _text(row.get("Direction")) or _infer_direction(row)
        row["Direction"] = direction
        counts[direction] = counts.get(direction, 0) + 1
        classified.append(row)
    return {"sector_classification": classified, "direction_counts": counts}


def _infer_direction(row: dict[str, Any]) -> str:
    haystack = " " + " ".join(
        _text(row.get(key)).lower()
        for key in ("Company Name", "Additional Decision-Useful Info", "Website URL", "Startup Stage")
    ) + " "
    for label, needles in SECTOR_RULES:
        if any(needle in haystack for needle in needles):
            return label
    return "Enterprise SaaS"


def score_icp(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    startups = _startup_list(_inputs(work_order), "sector_classification")
    scored: list[dict[str, Any]] = []
    for startup in startups:
        row = dict(startup)
        fit, evidence = _score_startup(row)
        row["Ohio Fit Score"] = str(fit)
        row["Evidence Quality Score"] = evidence
        scored.append(row)
    return {
        "icp_scores": scored,
        "score_summary": {
            "input_count": len(startups),
            "average_fit_score": round(sum(int(row.get("Ohio Fit Score") or 0) for row in scored) / max(1, len(scored)), 2),
            "high_fit_count": sum(1 for row in scored if int(row.get("Ohio Fit Score") or 0) >= 70),
        },
    }


def _score_startup(row: dict[str, Any]) -> tuple[int, int]:
    score = 20
    evidence = 0
    direction = _text(row.get("Direction"))
    if direction in {"AI / Generative Tech", "Enterprise SaaS", "Cybersecurity", "FinTech", "DeepTech", "HealthTech", "EdTech", "HRTech"}:
        score += 18
    if _text(row.get("Startup Stage")).lower() in {"pre-seed", "seed", "series a", "series-a", "early"}:
        score += 14
    elif _text(row.get("Startup Stage")):
        score += 7
    if _text(row.get("Website Verification Status")) == "Verified":
        score += 14
        evidence += 25
    if int(row.get("Founder LinkedIn Count") or 0) > 0:
        score += 10
        evidence += 20
    if _text(row.get("Additional Decision-Useful Info")):
        score += 10
        evidence += 20
    if _text(row.get("ARR")) or _text(row.get("MoM Growth")):
        score += 8
        evidence += 15
    if _text(row.get("Country of Incorporation")):
        score += 4
        evidence += 10
    if _text(row.get("Website Verification Status")) != "Verified":
        evidence = max(0, evidence - 15)
    return min(100, score), min(100, evidence)


def fill_synthetic_benchmarks(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    startups = _startup_list(_inputs(work_order), "icp_scores")
    filled: list[dict[str, Any]] = []
    synthetic_fields = 0
    for startup in startups:
        row = dict(startup)
        synthetic = _synthetic_benchmark(row)
        for key, value in synthetic.items():
            if not _text(row.get(key)):
                row[key] = value
                synthetic_fields += 1
        if any(_text(row.get(key)) for key in synthetic):
            row["Data Type"] = row.get("Data Type") or "synthetic benchmark data"
            row["Cohort Basis"] = row.get("Cohort Basis") or f"{row.get('Direction', 'General')} comparable startup cohort"
        filled.append(row)
    return {
        "synthetic_benchmarks": filled,
        "synthetic_summary": {"input_count": len(startups), "synthetic_fields_filled": synthetic_fields},
    }


def _synthetic_benchmark(row: dict[str, Any]) -> dict[str, str]:
    seed = int(hashlib.sha256(_normalize_name_key(row.get("Company Name")).encode("utf-8")).hexdigest()[:8], 16)
    stage = _text(row.get("Startup Stage")).lower()
    base_arr = 120_000 if "pre" in stage else 420_000 if "seed" in stage else 1_200_000
    arr = base_arr + (seed % base_arr)
    mrr = max(5_000, arr // 12)
    growth = 8 + seed % 18
    churn = 2 + seed % 5
    cac = 800 + seed % 4200
    contracts = 2 + seed % 14
    pipeline = contracts + 4 + seed % 22
    retention = 78 + seed % 18
    dau = 120 + seed % 2400
    mau = max(dau * 4, 900 + seed % 12000)
    direction = _text(row.get("Direction"))
    ai_approach = "AI-enabled workflow automation" if "AI" in direction or "SaaS" in direction else "Domain-specific software workflow"
    model = "B2B subscription" if direction not in {"Consumer", "Marketplace"} else "Usage / transaction revenue"
    return {
        "Synth ARR": f"${arr}",
        "Synth MRR": f"${mrr}",
        "Synth Revenue Growth %": f"{growth}%",
        "Synth Churn Rate %": f"{churn}%",
        "Synth Paid CAC": f"${cac}",
        "Synth Contracts Signed": str(contracts),
        "Synth Contracts Pipeline": str(pipeline),
        "Synth CAC Payback (mo)": str(5 + seed % 11),
        "Synth Retention %": f"{retention}%",
        "Synth User Growth %": f"{growth + 4}%",
        "Synth LTV/CAC": f"{round(2.0 + (seed % 30) / 10, 1)}x",
        "Synth DAU": str(dau),
        "Synth MAU": str(mau),
        "Synth AI Approach": ai_approach,
        "Synth Business Model": model,
    }


def judge_startups(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    startups = _startup_list(_inputs(work_order), "synthetic_benchmarks")
    judged: list[dict[str, Any]] = []
    counts = {"Approve": 0, "Reject": 0, "Needs manual verification": 0}
    for startup in startups:
        row = dict(startup)
        tag, reason = _judge(row)
        row["Judge Tag"] = tag
        row["Judge Reason"] = reason
        row["ICP Version"] = row.get("ICP Version") or "p2-ohio-v1"
        counts[tag] = counts.get(tag, 0) + 1
        judged.append(row)
    return {"judge_results": judged, "judge_summary": {"input_count": len(startups), **counts}}


def _judge(row: dict[str, Any]) -> tuple[str, str]:
    score = int(float(_text(row.get("Ohio Fit Score")) or 0))
    evidence = int(float(row.get("Evidence Quality Score") or 0))
    if _text(row.get("Website Verification Status")) != "Verified":
        return "Needs manual verification", "Company website is not verified, so ICP fit cannot be approved yet."
    if score >= 70 and evidence >= 45:
        return "Approve", f"Strong ICP fit ({score}/100) with enough founder, website, and decision-useful evidence."
    if score >= 58 and evidence >= 35:
        return "Needs manual verification", f"Potential ICP fit ({score}/100), but evidence quality is not strong enough for automatic approval."
    return "Reject", f"Below P2 ICP threshold ({score}/100) or lacks decision-useful evidence."


def build_suitable_list(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    inputs = _inputs(work_order)
    judged = _startup_list(inputs, "judge_results")
    external_keys = {
        _startup_key(row)
        for row in judged
        if _text(row.get("Source Tab") or row.get("_source_tab")).lower() == "new / external"
    }
    for row in inputs.get("external_startups", []) if isinstance(inputs.get("external_startups"), list) else []:
        if isinstance(row, dict):
            external_keys.add(_startup_key(row))
    suitable: list[dict[str, Any]] = []
    seen: set[str] = set()
    duplicate_count = 0
    excluded_duplicates: list[dict[str, Any]] = []
    rejected: list[dict[str, Any]] = []
    for row in judged:
        key = _startup_key(row)
        if row.get("Judge Tag") != "Approve":
            rejected.append({"company": row.get("Company Name"), "reason": row.get("Judge Reason")})
            continue
        if key in external_keys:
            duplicate_count += 1
            excluded_duplicates.append({"company": row.get("Company Name"), "reason": "already present in New / External"})
            continue
        if key in seen:
            duplicate_count += 1
            excluded_duplicates.append({"company": row.get("Company Name"), "reason": "duplicate inside P2 candidate set"})
            continue
        seen.add(key)
        suitable.append({header: _text(row.get(header)) for header in P2_STARTUP_HEADERS})
    return {
        "suitable_startups": suitable,
        "headers": P2_STARTUP_HEADERS,
        "excluded_duplicates": excluded_duplicates,
        "rejected_startups": rejected,
        "duplicates_removed": duplicate_count,
    }


def _normalize_name_key(value: Any) -> str:
    return re.sub(r"[^a-z0-9]+", "", _text(value).lower())


def _normalize_url_key(value: Any) -> str:
    domain = _url_domain(_clean_url(value))
    return re.sub(r"^m\.", "", domain)


def _startup_key(row: dict[str, Any]) -> str:
    url_key = _normalize_url_key(row.get("Website Final URL") or row.get("Website URL"))
    if url_key and url_key != "[tbc]":
        return f"url:{url_key}"
    return f"name:{_normalize_name_key(row.get('Company Name'))}"


def judge_quality(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    inputs = _inputs(work_order)
    suitable = _startup_list(inputs, "suitable_startups")
    reasons: list[str] = []
    seen: set[str] = set()
    for index, row in enumerate(suitable, start=1):
        missing = [header for header in ("Company Name", "Direction", "Judge Tag", "Website Verification Status", "Website Verification Note") if not _text(row.get(header))]
        if missing:
            reasons.append(f"row {index} missing required fields: {missing}")
        if row.get("Judge Tag") != "Approve":
            reasons.append(f"row {index} is not approved")
        key = _startup_key(row)
        if key in seen:
            reasons.append(f"row {index} duplicate company key: {key}")
        seen.add(key)
        if row.get("Website URL") == "[TBC]" and not _text(row.get("Website Verification Note")):
            reasons.append(f"row {index} has [TBC] URL without note")
        if _text(row.get("Founder LinkedIn URL(s)")) and any(sep in _text(row.get("Founder LinkedIn URL(s)")) for sep in (",", ";", "\n", "|")):
            reasons.append(f"row {index} founder links are not split")
    passed = not reasons
    score = 1.0 if passed else max(0.0, 1.0 - len(reasons) * 0.1)
    approval_package = {
        "approval_required": True,
        "output_tab": _text(inputs.get("output_tab") or P2_DEFAULT_OUTPUT_TAB),
        "headers": P2_STARTUP_HEADERS,
        "suitable_startups": suitable,
        "row_count": len(suitable),
        "reasons": reasons,
    }
    return {
        "passed": passed,
        "score": round(score, 2),
        "checks": {
            "schema_complete": not any("missing required fields" in reason for reason in reasons),
            "all_approved": not any("not approved" in reason for reason in reasons),
            "founder_links_split": not any("founder links" in reason for reason in reasons),
            "no_duplicates": not any("duplicate" in reason for reason in reasons),
            "tbc_rows_have_notes": not any("[TBC]" in reason for reason in reasons),
        },
        "reasons": reasons,
        "approval_package": approval_package,
        "suitable_startups": suitable,
    }


def sync_google_sheets(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    inputs = _inputs(work_order)
    if not bool(inputs.get("allow_google_sheet_write", False)):
        raise P2WorkerInputError("allow_google_sheet_write=true is required for P2 Google Sheets sync")
    spreadsheet_id = _text(inputs.get("spreadsheet_id") or os.environ.get("P2_GOOGLE_SHEET_ID"))
    if not spreadsheet_id:
        raise P2WorkerInputError("spreadsheet_id is required for P2 Google Sheets sync")
    approval_package = inputs.get("approval_package") if isinstance(inputs.get("approval_package"), dict) else inputs
    suitable = approval_package.get("suitable_startups", []) if isinstance(approval_package, dict) else []
    if not isinstance(suitable, list):
        raise P2WorkerInputError("approval package suitable_startups must be a list")
    output_tab = _text(inputs.get("output_tab") or approval_package.get("output_tab") or P2_DEFAULT_OUTPUT_TAB)
    headers = approval_package.get("headers") if isinstance(approval_package.get("headers"), list) else P2_STARTUP_HEADERS
    values = [headers] + [[_text(row.get(header)) if isinstance(row, dict) else "" for header in headers] for row in suitable]
    token = _google_access_token(_text(inputs.get("google_service_account_path") or os.environ.get("GOOGLE_SA_PATH")))
    result = _google_values_update(spreadsheet_id, output_tab, values, token)
    sync_result = {
        "spreadsheet_id": spreadsheet_id,
        "output_tab": output_tab,
        "mode": "replace",
        "row_count": len(suitable),
        "updated_range": result.get("updatedRange"),
        "updated_cells": result.get("updatedCells"),
    }
    return {
        "sync_result": sync_result,
        "external_actions": [{"type": "google_sheets_write", "status": "completed", **sync_result}],
    }


def build_metrics_report(work_order: dict[str, Any], _context: dict[str, Any]) -> dict[str, Any]:
    inputs = _inputs(work_order)
    raw = inputs.get("raw_startup_rows", [])
    normalized = inputs.get("normalized_startups", [])
    rejected_normalized = inputs.get("rejected_startups", [])
    verification_summary = inputs.get("verification_summary", {}) if isinstance(inputs.get("verification_summary"), dict) else {}
    judge_summary = inputs.get("judge_summary", {}) if isinstance(inputs.get("judge_summary"), dict) else {}
    suitable = inputs.get("suitable_startups", [])
    sync_result = inputs.get("sync_result", {})
    metrics = {
        "input_rows": len(raw) if isinstance(raw, list) else 0,
        "normalized_rows": len(normalized) if isinstance(normalized, list) else 0,
        "rejected_rows": len(rejected_normalized) if isinstance(rejected_normalized, list) else 0,
        "corrected_urls": int(verification_summary.get("corrected_urls") or 0),
        "tbc_urls": int(verification_summary.get("tbc_urls") or 0),
        "approved_startups": int(judge_summary.get("Approve") or 0),
        "rejected_startups": int(judge_summary.get("Reject") or 0),
        "needs_manual_verification": int(judge_summary.get("Needs manual verification") or 0),
        "suitable_rows": len(suitable) if isinstance(suitable, list) else 0,
        "duplicates_removed": int(inputs.get("duplicates_removed") or 0),
        "sheet_sync_result": sync_result if isinstance(sync_result, dict) else {},
    }
    return {"metrics": metrics, "summary": f"P2 suitable startup pipeline produced {metrics['suitable_rows']} suitable rows."}


HANDLERS = {
    "p2-sheet-reader": read_sheets,
    "p2-startup-normalizer": normalize_startups,
    "p2-founder-link-resolver": resolve_founder_links,
    "p2-website-verifier": verify_websites,
    "p2-sector-classifier": classify_sectors,
    "p2-icp-scorer": score_icp,
    "p2-synthetic-benchmarker": fill_synthetic_benchmarks,
    "p2-startup-judge": judge_startups,
    "p2-suitable-list-builder": build_suitable_list,
    "p2-quality-judge": judge_quality,
    "p2-google-sheets-syncer": sync_google_sheets,
    "p2-metrics-reporter": build_metrics_report,
    "read_sheets": read_sheets,
    "normalize_startups": normalize_startups,
    "resolve_founder_links": resolve_founder_links,
    "verify_websites": verify_websites,
    "classify_sectors": classify_sectors,
    "score_icp": score_icp,
    "fill_synthetic_benchmarks": fill_synthetic_benchmarks,
    "judge_startups": judge_startups,
    "build_suitable_list": build_suitable_list,
    "judge_quality": judge_quality,
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
        raise SystemExit(f"unknown P2 worker_profile/task_type: {work_order['worker_profile']} / {work_order['task_type']}")
    try:
        result = HANDLERS[handler_key](work_order, request["context"])
    except P2WorkerInputError as exc:
        sys.stderr.write(json.dumps({"error_type": "P2WorkerInputError", "message": str(exc)}, ensure_ascii=True))
        raise SystemExit(2) from None
    sys.stdout.write(json.dumps(result, ensure_ascii=True))


if __name__ == "__main__":
    main()
