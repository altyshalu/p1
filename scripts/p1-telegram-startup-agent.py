#!/usr/bin/env python3
from __future__ import annotations

import csv
from dataclasses import dataclass
from datetime import datetime, timedelta
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
from typing import Any
import urllib.parse
import urllib.request
from zoneinfo import ZoneInfo


DEFAULT_TZ = "Asia/Nicosia"
DEFAULT_STATE_DIR = "/opt/p1/runtime/p1_telegram_startup_agent"
DEFAULT_OUT_DIR = "/opt/p1/out"
DEFAULT_BATCH_SIZE = 10
DEFAULT_DAILY_TIME = "10:00"

APPROVED_FIELDS = [
    "Date Added",
    "Company Name",
    "Website URL",
    "Country",
    "Stage",
    "Category",
    "P1 Score",
    "Verdict",
    "Reasoning",
    "Source",
]


@dataclass(frozen=True)
class Config:
    telegram_token: str
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
        telegram_token=required("TELEGRAM_BOT_TOKEN"),
        chat_id=required("TELEGRAM_CHAT_ID"),
        message_thread_id=os.environ.get("TELEGRAM_MESSAGE_THREAD_ID", "").strip(),
        gemini_api_key=required("GEMINI_API_KEY"),
        timezone=os.environ.get("P1_STARTUP_TIMEZONE", DEFAULT_TZ).strip() or DEFAULT_TZ,
        daily_time=os.environ.get("P1_STARTUP_DAILY_TIME", DEFAULT_DAILY_TIME).strip() or DEFAULT_DAILY_TIME,
        batch_size=int(os.environ.get("P1_STARTUP_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
        state_dir=Path(os.environ.get("P1_STARTUP_STATE_DIR", DEFAULT_STATE_DIR)),
        out_dir=Path(os.environ.get("P1_STARTUP_OUT_DIR", DEFAULT_OUT_DIR)),
        candidates_path=os.environ.get("P1_STARTUP_CANDIDATES_PATH", "").strip(),
        google_sheet_id=os.environ.get("P1_STARTUP_GOOGLE_SHEET_ID", os.environ.get("P2_GOOGLE_SHEET_ID", "")).strip(),
        google_sheet_tab=os.environ.get("P1_STARTUP_GOOGLE_SHEET_TAB", "P1 Approved Startups").strip(),
        google_sa_path=os.environ.get("GOOGLE_SA_PATH", "").strip(),
    )


def required(key: str) -> str:
    value = os.environ.get(key, "").strip()
    if not value:
        raise SystemExit(f"missing required environment variable: {key}")
    return value


class TelegramClient:
    def __init__(self, token: str) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"

    def request(self, method: str, payload: dict[str, Any]) -> Any:
        req = urllib.request.Request(
            f"{self.base_url}/{method}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
        if data.get("ok") is not True:
            raise RuntimeError(f"Telegram {method} failed: {data}")
        return data.get("result")

    def get_updates(self, offset: int | None) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
        if offset is not None:
            payload["offset"] = offset
        result = self.request("getUpdates", payload)
        return result if isinstance(result, list) else []

    def send_message(self, chat_id: str, text: str, thread_id: str = "", reply_markup: dict[str, Any] | None = None) -> Any:
        payload: dict[str, Any] = {"chat_id": chat_id, "text": text[:3900], "disable_web_page_preview": True}
        if thread_id:
            payload["message_thread_id"] = int(thread_id)
        if reply_markup:
            payload["reply_markup"] = reply_markup
        return self.request("sendMessage", payload)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        self.request("answerCallbackQuery", payload)


def state_path(config: Config) -> Path:
    return config.state_dir / "state.json"


def load_state(config: Config) -> dict[str, Any]:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(config)
    if not path.exists():
        return {"offset": None, "sent_dates": [], "startups": {}, "pending_reject_comments": {}, "seen_keys": []}
    return json.loads(path.read_text(encoding="utf-8"))


def save_state(config: Config, state: dict[str, Any]) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    state_path(config).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def startup_id(startup: dict[str, Any]) -> str:
    raw = f"{startup.get('name')}|{startup.get('website')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def startup_key(startup: dict[str, Any]) -> str:
    website = str(startup.get("website") or "").lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
    if website:
        return f"url:{website}"
    return "name:" + re.sub(r"[^a-z0-9]+", "", str(startup.get("name") or "").lower())


def read_reject_feedback(config: Config, limit: int = 60) -> list[str]:
    path = config.state_dir / "reject_feedback.jsonl"
    if not path.exists():
        return []
    lines = path.read_text(encoding="utf-8").splitlines()[-limit:]
    comments: list[str] = []
    for line in lines:
        try:
            item = json.loads(line)
        except json.JSONDecodeError:
            continue
        comment = str(item.get("comment") or "").strip()
        if comment:
            comments.append(comment)
    return comments


def load_candidate_pool(config: Config) -> list[dict[str, Any]]:
    if config.candidates_path:
        return load_candidates_from_file(Path(config.candidates_path))
    feedback = read_reject_feedback(config)
    pool: list[dict[str, Any]] = []
    seen: set[str] = set()
    target = max(config.batch_size * 3, 75)
    for chunk_index in range(4):
        prompt = f"""
Generate 25 fresh Europe/UK AI-native startup candidates for a VC daily review queue.

Requirements:
- early-stage startups, AI-native or AI-enabled;
- no duplicate obvious companies;
- include official website URL when possible;
- avoid profiles similar to previous reject comments:
{json.dumps(feedback[-30:], ensure_ascii=False)}
- avoid companies already selected in this run:
{json.dumps(sorted(seen), ensure_ascii=False)}

Return JSON only:
{{"startups":[{{"name":"","website":"","country":"","stage":"","category":"","one_liner":"","source":""}}]}}
"""
        try:
            payload = gemini_json(config.gemini_api_key, prompt)
        except Exception as exc:
            print(f"candidate generation chunk {chunk_index + 1} failed: {exc}", flush=True)
            continue
        startups = payload.get("startups") if isinstance(payload, dict) else []
        for item in startups:
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
        raise RuntimeError("Gemini did not return any usable startup candidates.")
    return pool


def load_candidates_from_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("startups") if isinstance(payload, dict) else payload
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
        "category": first_text(item, "category", "Direction", "sector"),
        "one_liner": first_text(item, "one_liner", "headline", "description", "Additional Decision-Useful Info"),
        "source": first_text(item, "source", "Source") or "gemini_daily_sourcing",
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
        f"{prompt}\n\nReturn exactly one complete valid JSON object. Use double quotes for every property name and string. No markdown.",
    ]
    last_text = ""
    for attempt in prompts:
        body = {
            "contents": [{"parts": [{"text": attempt}]}],
            "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "maxOutputTokens": 8192},
        }
        request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(request, timeout=90) as response:
            raw = json.loads(response.read().decode("utf-8"))
        text = raw["candidates"][0]["content"]["parts"][0]["text"].strip().replace("```json", "").replace("```", "").strip()
        last_text = text
        parsed = parse_json_object(text)
        if isinstance(parsed, dict):
            return parsed
    repair_prompt = f"""
Fix this model output into one complete valid JSON object.
Keep only complete valid items if the output was truncated.
Return JSON only, no markdown.

Broken output:
{last_text[:12000]}
"""
    body = {
        "contents": [{"parts": [{"text": repair_prompt}]}],
        "generationConfig": {"responseMimeType": "application/json", "temperature": 0, "maxOutputTokens": 8192},
    }
    request = urllib.request.Request(url, data=json.dumps(body).encode("utf-8"), headers={"Content-Type": "application/json"}, method="POST")
    with urllib.request.urlopen(request, timeout=90) as response:
        raw = json.loads(response.read().decode("utf-8"))
    repaired = raw["candidates"][0]["content"]["parts"][0]["text"].strip().replace("```json", "").replace("```", "").strip()
    parsed = parse_json_object(repaired)
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
    candidate = text[start : end + 1]
    try:
        parsed = json.loads(candidate)
        return parsed if isinstance(parsed, dict) else None
    except json.JSONDecodeError:
        return None


def score_startup(config: Config, startup: dict[str, Any]) -> dict[str, Any]:
    feedback = read_reject_feedback(config)
    prompt = f"""
You are the P1 startup suitability judge for an AI-native VC daily queue.

Startup:
{json.dumps(startup, ensure_ascii=False)}

Reject-comment memory to learn from:
{json.dumps(feedback[-40:], ensure_ascii=False)}

Approve only if it is a credible Europe/UK startup with strong AI-native or AI-enabled product potential, startup-like profile, and enough information to review.
Reject if it is not a startup, not Europe/UK, agency/consulting-only, generic directory/content site, crypto spam, no official website, corporate product page, unclear AI relevance, or resembles the reject-comment memory.

Return JSON only with:
score: integer 0-100,
status: "gateway_eligible" or "reject" or "needs_enrichment",
reasoning: short practical reason,
category: short category
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
        "category": str(result.get("category") or startup.get("category") or "").strip(),
    }


def score_startups(config: Config, startups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feedback = read_reject_feedback(config)
    candidates = [
        {
            "index": index,
            "name": startup.get("name", ""),
            "website": startup.get("website", ""),
            "country": startup.get("country", ""),
            "stage": startup.get("stage", ""),
            "category": startup.get("category", ""),
            "one_liner": startup.get("one_liner", ""),
        }
        for index, startup in enumerate(startups)
    ]
    prompt = f"""
You are the P1 startup suitability judge for an AI-native VC daily queue.

Score these startup candidates:
{json.dumps(candidates, ensure_ascii=False)}

Reject-comment memory to learn from:
{json.dumps(feedback[-40:], ensure_ascii=False)}

Approve only if it is a credible Europe/UK startup with strong AI-native or AI-enabled product potential, startup-like profile, and enough information to review.
Reject if it is not a startup, not Europe/UK, agency/consulting-only, generic directory/content site, crypto spam, no official website, corporate product page, unclear AI relevance, or resembles the reject-comment memory.

Return JSON only:
{{"scores":[{{"index":0,"score":0,"status":"gateway_eligible|reject|needs_enrichment","reasoning":"short practical reason","category":"short category"}}]}}
"""
    result = gemini_json(config.gemini_api_key, prompt)
    rows = result.get("scores") if isinstance(result, dict) else []
    by_index: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        index = bounded_int(row.get("index"), 0, len(startups) - 1)
        score = bounded_int(row.get("score"), 0, 100)
        status = str(row.get("status") or "reject")
        if score >= 70 and status != "reject":
            status = "gateway_eligible"
        elif status == "gateway_eligible" and score < 70:
            status = "needs_enrichment"
        by_index[index] = {
            "score": score,
            "status": status,
            "reasoning": str(row.get("reasoning") or "").strip(),
            "category": str(row.get("category") or startups[index].get("category") or "").strip(),
        }
    return [
        by_index.get(
            index,
            {
                "score": 0,
                "status": "reject",
                "reasoning": "No batch score returned.",
                "category": startup.get("category", ""),
            },
        )
        for index, startup in enumerate(startups)
    ]


def bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))


def select_daily_startups(config: Config, state: dict[str, Any]) -> list[dict[str, Any]]:
    seen = set(state.get("seen_keys") or [])
    pool = load_candidate_pool(config)
    approved: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    candidate_keys: list[str] = []
    for startup in pool:
        if not startup.get("name"):
            continue
        key = startup_key(startup)
        if key in seen or key in candidate_keys:
            continue
        candidates.append(startup)
        candidate_keys.append(key)
    for offset in range(0, len(candidates), 20):
        chunk = candidates[offset : offset + 20]
        chunk_keys = candidate_keys[offset : offset + 20]
        print(f"scoring startup candidates {offset + 1}-{offset + len(chunk)}", flush=True)
        triage_rows = score_startups(config, chunk)
        for startup, key, triage in zip(chunk, chunk_keys, triage_rows, strict=False):
            startup = {**startup, "triage": triage, "id": startup_id(startup)}
            if triage["status"] == "gateway_eligible":
                approved.append(startup)
                seen.add(key)
            if len(approved) >= config.batch_size:
                break
        if len(approved) >= config.batch_size:
            break
    state["seen_keys"] = sorted(seen)
    return approved


def startup_message(index: int, startup: dict[str, Any]) -> str:
    triage = startup["triage"]
    return "\n".join(
        [
            f"{index}. {startup.get('name')}",
            f"{startup.get('website')}",
            f"{startup.get('country')} | {startup.get('stage')} | {triage.get('category') or startup.get('category')}",
            f"Score: {triage.get('score')} | {triage.get('status')}",
            f"{startup.get('one_liner')}",
            f"Why: {triage.get('reasoning')}",
        ]
    )


def buttons(startup_id_value: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": f"p1s:approve:{startup_id_value}"},
                {"text": "Reject", "callback_data": f"p1s:reject:{startup_id_value}"},
            ]
        ]
    }


def send_daily_batch(config: Config, state: dict[str, Any], telegram: TelegramClient, force: bool = False) -> None:
    now = datetime.now(ZoneInfo(config.timezone))
    today = now.date().isoformat()
    if not force and today in set(state.get("sent_dates") or []):
        return
    startups = select_daily_startups(config, state)
    telegram.send_message(config.chat_id, f"P1 daily startup queue: {len(startups)} startups for {today}", config.message_thread_id)
    state.setdefault("startups", {})
    for index, startup in enumerate(startups, start=1):
        state["startups"][startup["id"]] = startup
        telegram.send_message(config.chat_id, startup_message(index, startup), config.message_thread_id, buttons(startup["id"]))
    if not force:
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
    row = {
        "Date Added": datetime.now(ZoneInfo(config.timezone)).date().isoformat(),
        "Company Name": startup.get("name", ""),
        "Website URL": startup.get("website", ""),
        "Country": startup.get("country", ""),
        "Stage": startup.get("stage", ""),
        "Category": startup.get("triage", {}).get("category") or startup.get("category", ""),
        "P1 Score": startup.get("triage", {}).get("score", ""),
        "Verdict": "approve",
        "Reasoning": startup.get("triage", {}).get("reasoning", ""),
        "Source": startup.get("source", ""),
    }
    append_tsv(config.out_dir / "p1_approved_startups.tsv", APPROVED_FIELDS, row)
    if config.google_sheet_id and config.google_sa_path and Path(config.google_sa_path).exists():
        try:
            append_google_sheet(config, row)
            return "Approved and written to Google Sheet."
        except Exception as exc:
            append_tsv(config.out_dir / "p1_sheet_write_errors.tsv", ["time", "company", "error"], {"time": datetime.utcnow().isoformat(), "company": row["Company Name"], "error": str(exc)[:500]})
            return "Approved locally, but Google Sheet write failed. Saved to error log."
    return "Approved locally. Google Sheet credentials are not configured yet."


def append_google_sheet(config: Config, row: dict[str, Any]) -> None:
    from l2l3_protocol.workers.p1_operator_worker import _google_access_token, _request_json

    token = _google_access_token(config.google_sa_path)
    tab = config.google_sheet_tab
    encoded_range = urllib.parse.quote(f"{tab}!A:J", safe="")
    values = [[row[field] for field in APPROVED_FIELDS]]
    _request_json(
        f"https://sheets.googleapis.com/v4/spreadsheets/{config.google_sheet_id}/values/{encoded_range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        method="POST",
        token=token,
        body={"values": values},
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


def handle_callback(config: Config, state: dict[str, Any], telegram: TelegramClient, query: dict[str, Any]) -> None:
    data = str(query.get("data") or "")
    callback_id = str(query.get("id") or "")
    parts = data.split(":")
    if len(parts) != 3 or parts[0] != "p1s":
        return
    action, sid = parts[1], parts[2]
    startup = state.get("startups", {}).get(sid)
    if not isinstance(startup, dict):
        telegram.answer_callback(callback_id, "Startup not found in state.")
        return
    if action == "approve":
        message = approve_startup(config, startup)
        telegram.answer_callback(callback_id, "Approved")
        telegram.send_message(config.chat_id, f"{startup.get('name')}: {message}", config.message_thread_id)
        save_state(config, state)
        return
    if action == "reject":
        user = query.get("from") if isinstance(query.get("from"), dict) else {}
        key = str(user.get("id") or "unknown")
        state.setdefault("pending_reject_comments", {})[key] = sid
        save_state(config, state)
        telegram.answer_callback(callback_id, "Rejected")
        telegram.send_message(config.chat_id, f"Why reject {startup.get('name')}? Reply with the comment in this thread.", config.message_thread_id)


def handle_message(config: Config, state: dict[str, Any], telegram: TelegramClient, message: dict[str, Any]) -> None:
    text = str(message.get("text") or "").strip()
    user = message.get("from") if isinstance(message.get("from"), dict) else {}
    user_key = str(user.get("id") or "unknown")
    if user_key in state.get("pending_reject_comments", {}) and text and not text.startswith("/"):
        sid = state["pending_reject_comments"].pop(user_key)
        startup = state.get("startups", {}).get(sid, {})
        if isinstance(startup, dict):
            store_reject_comment(config, startup, text, user)
            telegram.send_message(config.chat_id, f"Saved reject feedback for {startup.get('name')}. I will use this in future scoring.", config.message_thread_id)
            save_state(config, state)
        return
    if text in {"/send_today", "/send_today@p1"}:
        send_daily_batch(config, state, telegram, force=True)
    elif text in {"/p1_status", "/p1_status@p1"}:
        telegram.send_message(config.chat_id, status_text(config, state), config.message_thread_id)


def status_text(config: Config, state: dict[str, Any]) -> str:
    approved_path = config.out_dir / "p1_approved_startups.tsv"
    feedback_path = config.state_dir / "reject_feedback.jsonl"
    approved_rows = max(0, len(approved_path.read_text(encoding="utf-8").splitlines()) - 1) if approved_path.exists() else 0
    feedback_rows = len(feedback_path.read_text(encoding="utf-8").splitlines()) if feedback_path.exists() else 0
    return "\n".join(
        [
            "P1 Telegram startup agent",
            f"daily_time: {config.daily_time} {config.timezone}",
            f"batch_size: {config.batch_size}",
            f"approved_local_rows: {approved_rows}",
            f"reject_feedback_rows: {feedback_rows}",
            f"google_sheet_configured: {bool(config.google_sheet_id and config.google_sa_path and Path(config.google_sa_path).exists())}",
        ]
    )


def next_daily_due(config: Config, state: dict[str, Any]) -> bool:
    now = datetime.now(ZoneInfo(config.timezone))
    hour, minute = [int(part) for part in config.daily_time.split(":", 1)]
    due_at = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if now < due_at:
        return False
    return now.date().isoformat() not in set(state.get("sent_dates") or [])


def run() -> None:
    config = load_config()
    config.state_dir.mkdir(parents=True, exist_ok=True)
    config.out_dir.mkdir(parents=True, exist_ok=True)
    telegram = TelegramClient(config.telegram_token)
    state = load_state(config)
    telegram.send_message(config.chat_id, "P1 Telegram startup agent is online. Use /send_today or /p1_status.", config.message_thread_id)
    while True:
        if next_daily_due(config, state):
            send_daily_batch(config, state, telegram)
        for update in telegram.get_updates(state.get("offset")):
            state["offset"] = int(update["update_id"]) + 1
            if isinstance(update.get("callback_query"), dict):
                handle_callback(config, state, telegram, update["callback_query"])
            elif isinstance(update.get("message"), dict):
                handle_message(config, state, telegram, update["message"])
            save_state(config, state)
        time.sleep(2)


if __name__ == "__main__":
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(
            "\n".join(
                [
                    "P1 Telegram startup agent",
                    "",
                    "Environment:",
                    "  P1_TELEGRAM_ENV_FILE=/opt/p1/.env",
                    "  TELEGRAM_BOT_TOKEN=...",
                    "  TELEGRAM_CHAT_ID=...",
                    "  TELEGRAM_MESSAGE_THREAD_ID=...  # optional p1 topic",
                    "  GEMINI_API_KEY=...",
                    "  P1_STARTUP_DAILY_TIME=10:00",
                    "  P1_STARTUP_TIMEZONE=Asia/Nicosia",
                    "  P1_STARTUP_BATCH_SIZE=10",
                    "",
                    "Telegram commands:",
                    "  /send_today",
                    "  /p1_status",
                ]
            )
        )
        raise SystemExit(0)
    run()
