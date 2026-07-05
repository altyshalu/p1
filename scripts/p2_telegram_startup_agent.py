#!/usr/bin/env python3
from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import time
from typing import Any
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


DEFAULT_TZ = "Asia/Nicosia"
DEFAULT_STATE_DIR = "/opt/p1/runtime/p2_telegram_startup_agent"
DEFAULT_OUT_DIR = "/opt/p1/out"
DEFAULT_BATCH_SIZE = 30
DEFAULT_DAILY_TIME = "10:00"
DEFAULT_SHEET_ID = "1ETOYOo792ZLUXppZ9zCKBDNZtAV_cn_isaBYJaef25Q"
DEFAULT_SHEET_TAB = "New / External"

APPROVED_FIELDS = [
    "Date Added",
    "Company Name",
    "Website URL",
    "Country",
    "Startup Stage",
    "Direction",
    "One-liner",
    "Founder LinkedIn URL(s)",
    "ARR",
    "US GTM Gap",
    "Ohio Fit Score",
    "P2 Status",
    "Verdict",
    "P2 Reasoning",
    "Source",
]

OHIO_ICP = """
OH.io Golden ICP for P2 startup sourcing:
- B2B software or AI startup, not B2C, not pure hardware, not services.
- Non-US origin is a strong positive signal: Barcelona, Berlin, Tel Aviv, Europe, Israel, LatAm, Asia, etc.
- Has product in production plus early PMF: first customers, revenue, pilots, or clear usage.
- Seed to Series A; post-PMF but before US scale.
- Willing to put a commercial/sales team in Columbus.
- Main fit signal: GTM gap. Strong product/engineering, weak or missing US sales. Revenue may exist but US expansion is stuck.
Reject:
- Already strong US sales or US commercial team.
- B2C, pure hardware, biotech/medtech without software core, consulting/services.
- Pre-product/pre-PMF.
- US-HQ with established commercial team.
- Late-stage/already scaled in the US.
Golden examples: Newo.ai and Testkube.
"""


@dataclass(frozen=True)
class Config:
    chat_id: str
    message_thread_id: str
    gemini_api_key: str
    timezone: str
    daily_time: str
    batch_size: int
    state_dir: Path
    out_dir: Path
    candidates_path: str
    google_sheet_id: str
    google_sheet_tab: str
    google_sa_path: str


def load_env(path: str | None) -> None:
    if not path:
        return
    env_path = Path(path)
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_config() -> Config:
    load_env(os.environ.get("P1_TELEGRAM_ENV_FILE", "/opt/p1/.env"))
    return Config(
        chat_id=required("TELEGRAM_CHAT_ID"),
        message_thread_id=os.environ.get("P2_TELEGRAM_MESSAGE_THREAD_ID", "").strip(),
        gemini_api_key=required("GEMINI_API_KEY"),
        timezone=os.environ.get("P2_STARTUP_TIMEZONE", DEFAULT_TZ).strip() or DEFAULT_TZ,
        daily_time=os.environ.get("P2_STARTUP_DAILY_TIME", DEFAULT_DAILY_TIME).strip() or DEFAULT_DAILY_TIME,
        batch_size=int(os.environ.get("P2_STARTUP_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
        state_dir=Path(os.environ.get("P2_STARTUP_STATE_DIR", DEFAULT_STATE_DIR)),
        out_dir=Path(os.environ.get("P2_STARTUP_OUT_DIR", DEFAULT_OUT_DIR)),
        candidates_path=os.environ.get("P2_STARTUP_CANDIDATES_PATH", "").strip(),
        google_sheet_id=os.environ.get("P2_STARTUP_GOOGLE_SHEET_ID", DEFAULT_SHEET_ID).strip(),
        google_sheet_tab=os.environ.get("P2_STARTUP_GOOGLE_SHEET_TAB", DEFAULT_SHEET_TAB).strip(),
        google_sa_path=os.environ.get("GOOGLE_SA_PATH", "").strip(),
    )


def required(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {key}")
    return value


def state_path(config: Config) -> Path:
    return config.state_dir / "state.json"


def load_state(config: Config) -> dict[str, Any]:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(config)
    if not path.exists():
        return {"sent_dates": [], "startups": {}, "pending_reject_comments": {}, "seen_keys": [], "decisions": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("startups", {})
    state.setdefault("pending_reject_comments", {})
    state.setdefault("seen_keys", [])
    state.setdefault("decisions", {})
    return state


def save_state(config: Config, state: dict[str, Any]) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    state_path(config).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def target_thread_id(config: Config, state: dict[str, Any]) -> str:
    return str(state.get("message_thread_id") or config.message_thread_id or "").strip()


def startup_id(startup: dict[str, Any]) -> str:
    raw = f"{startup.get('name')}|{startup.get('website')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def startup_key(startup: dict[str, Any]) -> str:
    website = str(startup.get("website") or "").lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
    if website:
        return f"url:{website}"
    return "name:" + re.sub(r"[^a-z0-9]+", "", str(startup.get("name") or "").lower())


def read_reject_feedback(config: Config, limit: int = 80) -> list[str]:
    path = config.state_dir / "reject_feedback.jsonl"
    if not path.exists():
        return []
    comments: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines()[-limit:]:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        comment = str(item.get("comment") or "").strip()
        if comment:
            comments.append(comment)
    return comments


def load_candidate_pool(config: Config) -> list[dict[str, Any]]:
    if config.candidates_path and Path(config.candidates_path).exists():
        return load_candidates_from_file(Path(config.candidates_path))
    feedback = read_reject_feedback(config)
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    target = max(config.batch_size * 5, 120)
    max_chunks = max(24, config.batch_size * 2)
    for chunk_index in range(max_chunks):
        chunk_size = min(5, target - len(pool))
        if chunk_size <= 0:
            break
        prompt = f"""
Generate {chunk_size} fresh real startup candidates for OH.io P2 daily review.

ICP:
{OHIO_ICP}

Avoid profiles similar to previous reject comments:
{json.dumps(feedback[-40:], ensure_ascii=False)}

Avoid companies already selected in this run:
{json.dumps(sorted(seen), ensure_ascii=False)}

Return JSON only:
{{"startups":[{{"name":"","website":"","country":"","stage":"","direction":"","one_liner":"","founder_linkedin":"","arr":"","us_gtm_gap":"","source":""}}]}}
"""
        try:
            payload = gemini_json(config.gemini_api_key, prompt)
        except Exception as exc:
            print(f"p2 candidate generation chunk {chunk_index + 1} failed: {exc}", flush=True)
            continue
        rows = payload.get("startups") if isinstance(payload, dict) else []
        for item in rows:
            if not isinstance(item, dict):
                continue
            startup = normalize_startup(item)
            key = startup_key(startup)
            if not startup.get("name") or key in seen:
                continue
            seen.add(key)
            pool.append(startup)
        if len(pool) >= target:
            break
    if not pool:
        raise RuntimeError("Gemini did not return usable P2 startup candidates.")
    return pool


def load_candidates_from_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("startups") or payload.get("candidates") if isinstance(payload, dict) else payload
        return [normalize_startup(item) for item in rows if isinstance(item, dict)]
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8", newline="") as handle:
        return [normalize_startup(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def normalize_startup(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "name": first_text(item, "name", "Company Name", "company"),
        "website": clean_url(first_text(item, "website", "Website URL", "url")),
        "country": first_text(item, "country", "Country", "Country of Incorporation"),
        "stage": first_text(item, "stage", "Startup Stage"),
        "direction": first_text(item, "direction", "Direction", "category", "sector"),
        "one_liner": first_text(item, "one_liner", "headline", "description", "Additional Decision-Useful Info"),
        "founder_linkedin": clean_url(first_text(item, "founder_linkedin", "Founder LinkedIn URL(s)", "linkedin")),
        "arr": first_text(item, "arr", "ARR"),
        "us_gtm_gap": first_text(item, "us_gtm_gap", "US GTM Gap"),
        "source": first_text(item, "source", "Source") or "p2_ohio_icp_sourcing",
    }


def first_text(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is not None and str(value).strip():
            return re.sub(r"\s+", " ", str(value)).strip()
    return ""


def clean_url(value: str) -> str:
    raw = value.strip()
    if not raw:
        return ""
    match = re.search(r"https?://[^\s,;|)]+", raw)
    if match:
        raw = match.group(0)
    if raw and not raw.startswith(("http://", "https://")):
        raw = "https://" + raw
    return raw.rstrip(".,;)]")


def gemini_json(api_key: str, prompt: str) -> dict[str, Any]:
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={api_key}"
    prompts = [
        prompt,
        f"{prompt}\n\nReturn exactly one complete valid JSON object. Use double quotes. No markdown.",
    ]
    last_text = ""
    for attempt in prompts:
        body = {
            "contents": [{"parts": [{"text": attempt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "maxOutputTokens": 16384},
        }
        req = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=90) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw["candidates"][0]["content"]["parts"][0]["text"].strip().replace("```json", "").replace("```", "").strip()
        last_text = text
        parsed = parse_json_object(text)
        if isinstance(parsed, dict):
            return parsed
    raise RuntimeError(f"Gemini returned invalid JSON: {last_text[:500]}")


def parse_json_object(text: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(text)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    end = text.rfind("}")
    if start < 0 or end <= start:
        return None
    try:
        parsed = json.loads(text[start : end + 1])
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def score_startup(config: Config, startup: dict[str, Any]) -> dict[str, Any]:
    feedback = read_reject_feedback(config)
    prompt = f"""
You are the OH.io Golden ICP judge for P2 startup sourcing.

Startup:
{json.dumps(startup, ensure_ascii=False)}

ICP:
{OHIO_ICP}

Reject-comment memory:
{json.dumps(feedback[-40:], ensure_ascii=False)}

Approve only if it is a B2B software/AI startup, non-US or internationally originated, seed-Series A/post-PMF, has product and early customer/revenue proof, and has a meaningful US GTM gap that OH.io can help with.
Reject if B2C, pure hardware, services/consulting, pre-PMF, US-established, late-stage, or already strong in US sales.

Return JSON only:
{{"score":0,"status":"gateway_eligible|reject|needs_enrichment","reasoning":"short reason","direction":"short sector","us_gtm_gap":"short gap evidence"}}
"""
    result = gemini_json(config.gemini_api_key, prompt)
    score = bounded_int(result.get("score"), 0, 100)
    status = str(result.get("status") or "reject")
    if score >= 70 and status != "reject":
        status = "gateway_eligible"
    elif status == "gateway_eligible" and score < 70:
        status = "needs_enrichment"
    return {
        "score": score,
        "status": status,
        "reasoning": str(result.get("reasoning") or "").strip(),
        "direction": str(result.get("direction") or startup.get("direction") or "").strip(),
        "us_gtm_gap": str(result.get("us_gtm_gap") or startup.get("us_gtm_gap") or "").strip(),
    }


def bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))


def select_daily_startups(config: Config, state: dict[str, Any]) -> list[dict[str, Any]]:
    seen = set(state.get("seen_keys") or [])
    approved: list[dict[str, Any]] = []
    for startup in load_candidate_pool(config):
        key = startup_key(startup)
        if not startup.get("name") or key in seen:
            continue
        triage = score_startup(config, startup)
        startup = {**startup, "triage": triage, "id": startup_id(startup)}
        if triage["status"] == "gateway_eligible":
            approved.append(startup)
            seen.add(key)
        if len(approved) >= config.batch_size:
            break
        time.sleep(0.05)
    state["seen_keys"] = sorted(seen)
    return approved


def startup_message(index: int, startup: dict[str, Any]) -> str:
    triage = startup["triage"]
    return "\n".join(
        [
            f"{index}. {startup.get('name')}",
            f"{startup.get('website')}",
            f"{startup.get('country')} | {startup.get('stage')} | {triage.get('direction') or startup.get('direction')}",
            f"Score: {triage.get('score')} | {triage.get('status')}",
            f"{startup.get('one_liner')}",
            f"US GTM gap: {triage.get('us_gtm_gap') or startup.get('us_gtm_gap')}",
            f"Why: {triage.get('reasoning')}",
        ]
    )


def buttons(startup_id_value: str) -> dict[str, Any]:
    return {"inline_keyboard": [[{"text": "Approve", "callback_data": f"p2s:approve:{startup_id_value}"}, {"text": "Reject", "callback_data": f"p2s:reject:{startup_id_value}"}]]}


def status_button(status: str) -> dict[str, Any]:
    label = "Approved" if status == "approved" else "Rejected"
    return {"inline_keyboard": [[{"text": label, "callback_data": f"p2s:noop:{status}"}]]}


def send_daily_batch(config: Config, state: dict[str, Any], telegram: Any, force: bool = False) -> None:
    now = datetime.now(ZoneInfo(config.timezone))
    today = now.date().isoformat()
    if not force and today in set(state.get("sent_dates") or []):
        return
    thread_id = target_thread_id(config, state)
    if not thread_id:
        print("p2 startup batch skipped: missing P2 message_thread_id. Send /p2_bind inside the p2 topic.", flush=True)
        return
    startups = select_daily_startups(config, state)
    if len(startups) < config.batch_size:
        print(f"p2 startup batch incomplete: selected {len(startups)} of {config.batch_size}", flush=True)
    telegram.send_message(config.chat_id, f"P2 daily startup queue: {len(startups)} startups for {today}", thread_id)
    state.setdefault("startups", {})
    for index, startup in enumerate(startups, start=1):
        state["startups"][startup["id"]] = startup
        sent = telegram.send_message(config.chat_id, startup_message(index, startup), thread_id, buttons(startup["id"]))
        if isinstance(sent, dict) and sent.get("message_id"):
            state["startups"][startup["id"]]["telegram_message_id"] = sent["message_id"]
    if not force and len(startups) >= config.batch_size:
        state.setdefault("sent_dates", []).append(today)
    save_state(config, state)


def append_tsv(path: Path, fields: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def approve_startup(config: Config, startup: dict[str, Any]) -> str:
    triage = startup.get("triage", {})
    row = {
        "Date Added": datetime.now(ZoneInfo(config.timezone)).date().isoformat(),
        "Company Name": startup.get("name", ""),
        "Website URL": startup.get("website", ""),
        "Country": startup.get("country", ""),
        "Startup Stage": startup.get("stage", ""),
        "Direction": triage.get("direction") or startup.get("direction", ""),
        "One-liner": startup.get("one_liner", ""),
        "Founder LinkedIn URL(s)": startup.get("founder_linkedin", ""),
        "ARR": startup.get("arr", ""),
        "US GTM Gap": triage.get("us_gtm_gap") or startup.get("us_gtm_gap", ""),
        "Ohio Fit Score": triage.get("score", ""),
        "P2 Status": triage.get("status", ""),
        "Verdict": "approve",
        "P2 Reasoning": triage.get("reasoning", ""),
        "Source": startup.get("source", ""),
    }
    append_tsv(config.out_dir / "p2_approved_startups.tsv", APPROVED_FIELDS, row)
    if config.google_sheet_id and config.google_sa_path and Path(config.google_sa_path).exists():
        try:
            append_google_sheet(config, row)
            return "Approved and appended to P2 Google Sheet."
        except Exception as exc:
            append_tsv(config.out_dir / "p2_sheet_write_errors.tsv", ["time", "company", "error"], {"time": datetime.utcnow().isoformat(), "company": row["Company Name"], "error": str(exc)[:500]})
            return "Approved locally, but P2 Google Sheet write failed. Saved to error log."
    return "Approved locally. P2 Google Sheet credentials are not configured yet."


def append_google_sheet(config: Config, row: dict[str, Any]) -> None:
    from l2l3_protocol.workers.p1_operator_worker import _google_access_token, _request_json

    token = _google_access_token(config.google_sa_path)
    ensure_google_sheet_headers(config, token)
    encoded_range = urllib.parse.quote(f"{config.google_sheet_tab}!A:O", safe="")
    _request_json(
        f"https://sheets.googleapis.com/v4/spreadsheets/{config.google_sheet_id}/values/{encoded_range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        method="POST",
        token=token,
        body={"values": [[row[field] for field in APPROVED_FIELDS]]},
    )


def ensure_google_sheet_headers(config: Config, token: str) -> None:
    from l2l3_protocol.workers.p1_operator_worker import _request_json

    metadata = _request_json(f"https://sheets.googleapis.com/v4/spreadsheets/{config.google_sheet_id}?fields=sheets.properties", token=token)
    sheets = metadata.get("sheets", []) if isinstance(metadata, dict) else []
    existing = {str(item.get("properties", {}).get("title") or "") for item in sheets if isinstance(item, dict)}
    if config.google_sheet_tab not in existing:
        _request_json(
            f"https://sheets.googleapis.com/v4/spreadsheets/{config.google_sheet_id}:batchUpdate",
            method="POST",
            token=token,
            body={"requests": [{"addSheet": {"properties": {"title": config.google_sheet_tab}}}]},
        )
    encoded_row = urllib.parse.quote(f"{config.google_sheet_tab}!1:1", safe="")
    existing_values = _request_json(f"https://sheets.googleapis.com/v4/spreadsheets/{config.google_sheet_id}/values/{encoded_row}", token=token).get("values", [])
    if not existing_values:
        _request_json(
            f"https://sheets.googleapis.com/v4/spreadsheets/{config.google_sheet_id}/values/{encoded_row}?valueInputOption=RAW",
            method="PUT",
            token=token,
            body={"values": [APPROVED_FIELDS]},
        )


def store_reject_comment(config: Config, startup: dict[str, Any], comment: str, user: dict[str, Any]) -> None:
    path = config.state_dir / "reject_feedback.jsonl"
    item = {
        "time": datetime.utcnow().isoformat(),
        "startup_id": startup.get("id"),
        "company": startup.get("name"),
        "website": startup.get("website"),
        "comment": comment,
        "user_id": user.get("id"),
        "username": user.get("username"),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(item, ensure_ascii=False) + "\n")


def handle_callback(config: Config, state: dict[str, Any], telegram: Any, query: dict[str, Any]) -> None:
    data = str(query.get("data") or "")
    callback_id = str(query.get("id") or "")
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "p2s":
        return
    action, sid = parts[1], parts[2]
    if action == "noop":
        telegram.answer_callback(callback_id, "Already handled.")
        return
    startup = state.get("startups", {}).get(sid)
    if not isinstance(startup, dict):
        telegram.answer_callback(callback_id, "Startup not found in state.")
        return
    decisions = state.setdefault("decisions", {})
    if isinstance(decisions.get(sid), dict):
        status = str(decisions[sid].get("status") or "handled")
        telegram.answer_callback(callback_id, f"Already {status}.")
        edit_callback_buttons(config, telegram, query, status)
        return
    if action == "approve":
        message = approve_startup(config, startup)
        decisions[sid] = {"status": "approved", "time": datetime.utcnow().isoformat()}
        telegram.answer_callback(callback_id, "Approved")
        edit_callback_buttons(config, telegram, query, "approved")
        telegram.send_message(config.chat_id, f"{startup.get('name')}: {message}", target_thread_id(config, state))
        save_state(config, state)
        return
    if action == "reject":
        user = query.get("from") if isinstance(query.get("from"), dict) else {}
        key = str(user.get("id") or "unknown")
        decisions[sid] = {"status": "rejected", "time": datetime.utcnow().isoformat(), "comment_pending": True}
        state.setdefault("pending_reject_comments", {})[key] = sid
        save_state(config, state)
        telegram.answer_callback(callback_id, "Rejected")
        edit_callback_buttons(config, telegram, query, "rejected")
        telegram.send_message(config.chat_id, f"Why reject {startup.get('name')}? Reply with the comment in this thread.", target_thread_id(config, state))


def edit_callback_buttons(config: Config, telegram: Any, query: dict[str, Any], status: str) -> None:
    message = query.get("message") if isinstance(query.get("message"), dict) else {}
    try:
        message_id = int(message.get("message_id"))
    except (TypeError, ValueError):
        return
    try:
        telegram.edit_reply_markup(config.chat_id, message_id, status_button(status))
    except Exception as exc:
        print(f"p2 telegram edit warning: {exc}", flush=True)


def handle_message(config: Config, state: dict[str, Any], telegram: Any, message: dict[str, Any]) -> bool:
    text = str(message.get("text") or "").strip()
    user = message.get("from") if isinstance(message.get("from"), dict) else {}
    user_key = str(user.get("id") or "unknown")
    current_thread_id = str(message.get("message_thread_id") or "").strip()
    if text in {"/p2_bind", "/p2_bind@p1"}:
        if not current_thread_id:
            telegram.send_message(config.chat_id, "Send /p2_bind inside the p2 topic, not the main chat.", "")
            return True
        state["message_thread_id"] = current_thread_id
        save_state(config, state)
        telegram.send_message(config.chat_id, f"P2 bound to this topic. message_thread_id={current_thread_id}", current_thread_id)
        return True
    if user_key in state.get("pending_reject_comments", {}) and text and not text.startswith("/"):
        sid = state["pending_reject_comments"].pop(user_key)
        startup = state.get("startups", {}).get(sid, {})
        if isinstance(startup, dict):
            store_reject_comment(config, startup, text, user)
            decision = state.setdefault("decisions", {}).setdefault(sid, {"status": "rejected"})
            decision["comment"] = text
            decision["comment_pending"] = False
            telegram.send_message(config.chat_id, f"Saved P2 reject feedback for {startup.get('name')}. I will use this in future scoring.", target_thread_id(config, state))
            save_state(config, state)
        return True
    if text in {"/p2_send_today", "/p2_send_today@p1"}:
        send_daily_batch(config, state, telegram, force=True)
        return True
    if text in {"/p2_status", "/p2_status@p1"}:
        telegram.send_message(config.chat_id, status_text(config, state), target_thread_id(config, state) or current_thread_id)
        return True
    return False


def status_text(config: Config, state: dict[str, Any]) -> str:
    feedback_path = config.state_dir / "reject_feedback.jsonl"
    feedback_rows = len(feedback_path.read_text(encoding="utf-8").splitlines()) if feedback_path.exists() else 0
    return "\n".join(
        [
            "P2 Telegram startup agent",
            f"daily_time: {config.daily_time} {config.timezone}",
            f"batch_size: {config.batch_size}",
            f"message_thread_id: {target_thread_id(config, state) or '<missing: send /p2_bind in p2 topic>'}",
            f"sent_dates: {len(state.get('sent_dates', []))}",
            f"startups_in_state: {len(state.get('startups', {}))}",
            f"reject_feedback_rows: {feedback_rows}",
            f"google_sheet: {config.google_sheet_id} / {config.google_sheet_tab}",
        ]
    )


def next_daily_due(config: Config, state: dict[str, Any]) -> bool:
    if not target_thread_id(config, state):
        return False
    now = datetime.now(ZoneInfo(config.timezone))
    hour, minute = [int(part) for part in config.daily_time.split(":", 1)]
    due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < due_at:
        return False
    return now.date().isoformat() not in set(state.get("sent_dates") or [])
