#!/usr/bin/env python3
from __future__ import annotations

import csv
from dataclasses import dataclass, replace
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
import urllib.error
from zoneinfo import ZoneInfo


DEFAULT_TZ = "Asia/Nicosia"
DEFAULT_STATE_DIR = "/opt/p1/runtime/p1_telegram_angel_agent"
DEFAULT_OUT_DIR = "/opt/p1/out"
DEFAULT_BATCH_SIZE = 30
DEFAULT_DAILY_TIME = "10:00"

APPROVED_FIELDS = [
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
    google_adc_path: str
    drive_folder_id: str
    drive_file_name: str


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
        timezone=os.environ.get("P1_ANGEL_TIMEZONE", DEFAULT_TZ).strip() or DEFAULT_TZ,
        daily_time=os.environ.get("P1_ANGEL_DAILY_TIME", DEFAULT_DAILY_TIME).strip() or DEFAULT_DAILY_TIME,
        batch_size=int(os.environ.get("P1_ANGEL_BATCH_SIZE", DEFAULT_BATCH_SIZE)),
        state_dir=Path(os.environ.get("P1_ANGEL_STATE_DIR", DEFAULT_STATE_DIR)),
        out_dir=Path(os.environ.get("P1_ANGEL_OUT_DIR", DEFAULT_OUT_DIR)),
        candidates_path=os.environ.get("P1_ANGEL_CANDIDATES_PATH", "").strip(),
        google_sheet_id=os.environ.get("P1_ANGEL_GOOGLE_SHEET_ID", os.environ.get("P1_GOOGLE_SHEET_ID", os.environ.get("P2_GOOGLE_SHEET_ID", ""))).strip(),
        google_sheet_tab=os.environ.get("P1_ANGEL_GOOGLE_SHEET_TAB", "P1 Approved Angels").strip(),
        google_sa_path=os.environ.get("GOOGLE_SA_PATH", "").strip(),
        google_adc_path=os.environ.get("GOOGLE_ADC_PATH", "/root/.config/gcloud/application_default_credentials.json").strip(),
        drive_folder_id=os.environ.get("P1_ANGEL_DRIVE_FOLDER_ID", "").strip(),
        drive_file_name=os.environ.get("P1_ANGEL_DRIVE_FILE_NAME", "limpid leads").strip() or "limpid leads",
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
        try:
            with urllib.request.urlopen(req, timeout=90) as response:
                data = json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise TelegramError(exc.code, f"Telegram {method} HTTP {exc.code}: {body[:500]}") from exc
        if data.get("ok") is not True:
            raise TelegramError(0, f"Telegram {method} failed: {data}")
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

    def edit_reply_markup(self, chat_id: str, message_id: int, reply_markup: dict[str, Any]) -> None:
        payload: dict[str, Any] = {"chat_id": chat_id, "message_id": message_id, "reply_markup": reply_markup}
        self.request("editMessageReplyMarkup", payload)

    def answer_callback(self, callback_id: str, text: str = "") -> None:
        payload: dict[str, Any] = {"callback_query_id": callback_id}
        if text:
            payload["text"] = text
        self.request("answerCallbackQuery", payload)


class TelegramError(RuntimeError):
    def __init__(self, status_code: int, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code


def state_path(config: Config) -> Path:
    return config.state_dir / "state.json"


def load_state(config: Config) -> dict[str, Any]:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    path = state_path(config)
    if not path.exists():
        return {"offset": None, "sent_dates": [], "angels": {}, "pending_reject_comments": {}, "seen_keys": [], "decisions": {}}
    state = json.loads(path.read_text(encoding="utf-8"))
    state.setdefault("decisions", {})
    state.setdefault("pending_reject_comments", {})
    state.setdefault("angels", {})
    return state


def save_state(config: Config, state: dict[str, Any]) -> None:
    config.state_dir.mkdir(parents=True, exist_ok=True)
    state_path(config).write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def angel_id(angel: dict[str, Any]) -> str:
    raw = f"{angel.get('name')}|{angel.get('linkedin_url')}"
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:12]


def angel_key(angel: dict[str, Any]) -> str:
    linkedin_url = str(angel.get("linkedin_url") or "").lower().strip().removeprefix("https://").removeprefix("http://").removeprefix("www.").rstrip("/")
    if linkedin_url:
        return f"url:{linkedin_url}"
    return "name:" + re.sub(r"[^a-z0-9]+", "", str(angel.get("name") or "").lower())


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
    file_pool: list[dict[str, Any]] = []
    if config.candidates_path:
        file_path = Path(config.candidates_path)
        if file_path.exists():
            file_pool = load_candidates_from_file(file_path)
    feedback = read_reject_feedback(config)
    pool: list[dict[str, Any]] = list(file_pool)
    seen: set[str] = {angel_key(angel) for angel in pool}
    target = max(config.batch_size * 3, 75)
    if len(pool) >= target:
        return pool
    for chunk_index in range(4):
        prompt = f"""
Generate 25 fresh worldwide operator-angel candidates for a VC daily review queue.

Requirements:
- individual angels, scouts, micro-fund operators, or founder/operator check-writers;
- must have B2C, consumer, marketplace, gaming, viral fintech, or PLG/operator DNA;
- no duplicate obvious people;
- include LinkedIn URL when possible;
- include city/country/headline;
- prefer publicly known real people with evidence that can be checked;
- avoid profiles similar to previous reject comments:
{json.dumps(feedback[-30:], ensure_ascii=False)}
- avoid people already selected in this run:
{json.dumps(sorted(seen), ensure_ascii=False)}

Return JSON only:
{{"angels":[{{"name":"","linkedin_url":"","city":"","country":"","headline":"","evidence":[""],"source":""}}]}}
"""
        try:
            payload = gemini_json(config.gemini_api_key, prompt)
        except Exception as exc:
            print(f"candidate generation chunk {chunk_index + 1} failed: {exc}", flush=True)
            continue
        angels = payload.get("angels") if isinstance(payload, dict) else []
        for item in angels:
            if not isinstance(item, dict):
                continue
            angel = normalize_angel(item)
            key = angel_key(angel)
            if not angel.get("name") or key in seen:
                continue
            seen.add(key)
            pool.append(angel)
        if len(pool) >= target:
            break
    if not pool:
        raise RuntimeError("Gemini did not return any usable angel candidates.")
    return pool


def load_candidates_from_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".json":
        payload = json.loads(path.read_text(encoding="utf-8"))
        rows = payload.get("angels") or payload.get("candidates") if isinstance(payload, dict) else payload
        return [normalize_angel(item) for item in rows if isinstance(item, dict)]
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    with path.open(encoding="utf-8", newline="") as handle:
        return [normalize_angel(row) for row in csv.DictReader(handle, delimiter=delimiter)]


def normalize_angel(item: dict[str, Any]) -> dict[str, Any]:
    evidence = item.get("evidence")
    if isinstance(evidence, str):
        evidence_values = [part.strip() for part in re.split(r"\s*\|\s*|\n", evidence) if part.strip()]
    elif isinstance(evidence, list):
        evidence_values = [str(part).strip() for part in evidence if str(part).strip()]
    else:
        evidence_values = []
    normalized = {
        "name": first_text(item, "name", "Name"),
        "linkedin_url": clean_url(first_text(item, "linkedin_url", "LinkedIn", "LinkedIn URL", "url")),
        "city": first_text(item, "city", "City"),
        "country": first_text(item, "country", "Country"),
        "headline": first_text(item, "headline", "Headline", "description", "one_liner"),
        "evidence": evidence_values,
        "source": first_text(item, "source", "Source") or "p1_angel_sourcing",
    }
    if isinstance(item.get("triage"), dict):
        normalized["triage"] = item["triage"]
    return normalized


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


def score_angel(config: Config, angel: dict[str, Any]) -> dict[str, Any]:
    feedback = read_reject_feedback(config)
    prompt = f"""
You are the P1 angel suitability judge for an AI-native VC daily queue.

Angel:
{json.dumps(angel, ensure_ascii=False)}

Reject-comment memory to learn from:
{json.dumps(feedback[-40:], ensure_ascii=False)}

Approve only if it has BOTH real B2C/consumer/marketplace/gaming/viral fintech/PLG operator experience AND personal angel/check-writer/scout/micro-fund evidence.
Reject VC-only, advisor-only, mentor-only, B2B SaaS-only, consulting-only, corporate finance, commercial banking, biotech, defense, medical equipment, heavy industry, real estate, Cyprus, no personal investing evidence, or profiles resembling reject memory.

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
        "category": str(result.get("category") or angel.get("category") or "").strip(),
    }


def score_angels(config: Config, angels: list[dict[str, Any]]) -> list[dict[str, Any]]:
    feedback = read_reject_feedback(config)
    candidates = [
        {
            "index": index,
            "name": angel.get("name", ""),
            "linkedin_url": angel.get("linkedin_url", ""),
            "city": angel.get("city", ""),
            "country": angel.get("country", ""),
            "headline": angel.get("headline", ""),
            "evidence": angel.get("evidence", []),
        }
        for index, angel in enumerate(angels)
    ]
    prompt = f"""
You are the P1 angel suitability judge for an AI-native VC daily queue.

Score these angel candidates:
{json.dumps(candidates, ensure_ascii=False)}

Reject-comment memory to learn from:
{json.dumps(feedback[-40:], ensure_ascii=False)}

Approve only if it has BOTH real B2C/consumer/marketplace/gaming/viral fintech/PLG operator experience AND personal angel/check-writer/scout/micro-fund evidence.
Reject VC-only, advisor-only, mentor-only, B2B SaaS-only, consulting-only, corporate finance, commercial banking, biotech, defense, medical equipment, heavy industry, real estate, Cyprus, no personal investing evidence, or profiles resembling reject memory.

Return JSON only:
{{"scores":[{{"index":0,"score":0,"status":"gateway_eligible|reject|needs_enrichment","reasoning":"short practical reason","category":"short category"}}]}}
"""
    result = gemini_json(config.gemini_api_key, prompt)
    rows = result.get("scores") if isinstance(result, dict) else []
    by_index: dict[int, dict[str, Any]] = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        index = bounded_int(row.get("index"), 0, len(angels) - 1)
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
            "category": str(row.get("category") or angels[index].get("category") or "").strip(),
        }
    return [
        by_index.get(
            index,
            {
                "score": 0,
                "status": "reject",
                "reasoning": "No batch score returned.",
                "category": angel.get("category", ""),
            },
        )
        for index, angel in enumerate(angels)
    ]


def bounded_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        number = int(value)
    except (TypeError, ValueError):
        number = 0
    return max(minimum, min(maximum, number))


def select_daily_angels(config: Config, state: dict[str, Any]) -> list[dict[str, Any]]:
    seen = set(state.get("seen_keys") or [])
    pool = load_candidate_pool(config)
    approved: list[dict[str, Any]] = []
    candidates: list[dict[str, Any]] = []
    candidate_keys: list[str] = []
    for angel in pool:
        if not angel.get("name"):
            continue
        key = angel_key(angel)
        if key in seen or key in candidate_keys:
            continue
        candidates.append(angel)
        candidate_keys.append(key)
    for offset in range(0, len(candidates), 20):
        chunk = candidates[offset : offset + 20]
        chunk_keys = candidate_keys[offset : offset + 20]
        pretriaged = [angel.get("triage") if isinstance(angel.get("triage"), dict) else None for angel in chunk]
        if all(row and row.get("status") == "gateway_eligible" for row in pretriaged):
            triage_rows = [dict(row) for row in pretriaged if row]
        else:
            for idx, angel in enumerate(chunk):
                if pretriaged[idx] and pretriaged[idx].get("status") == "gateway_eligible":
                    continue
                triage = score_angel(config, angel)
                chunk[idx] = {**angel, "triage": triage}
                pretriaged[idx] = triage
                time.sleep(0.05)
            triage_rows = [dict(row) if row else {"score": 0, "status": "reject", "reasoning": "No triage returned."} for row in pretriaged]
        print(f"scoring angel candidates {offset + 1}-{offset + len(chunk)}", flush=True)
        for angel, key, triage in zip(chunk, chunk_keys, triage_rows, strict=False):
            angel = {**angel, "triage": triage, "id": angel_id(angel)}
            if triage["status"] == "gateway_eligible":
                approved.append(angel)
                seen.add(key)
            if len(approved) >= config.batch_size:
                break
        if len(approved) >= config.batch_size:
            break
    state["seen_keys"] = sorted(seen)
    return approved


def angel_message(index: int, angel: dict[str, Any]) -> str:
    triage = angel["triage"]
    return "\n".join(
        [
            f"{index}. {angel.get('name')}",
            f"{angel.get('linkedin_url')}",
            f"{angel.get('city')}, {angel.get('country')}",
            f"Score: {triage.get('score')} | {triage.get('status')}",
            f"{angel.get('headline')}",
            f"Why: {triage.get('reasoning')}",
        ]
    )


def buttons(angel_id_value: str) -> dict[str, Any]:
    return {
        "inline_keyboard": [
            [
                {"text": "Approve", "callback_data": f"p1a:approve:{angel_id_value}"},
                {"text": "Reject", "callback_data": f"p1a:reject:{angel_id_value}"},
            ]
        ]
    }


def status_button(status: str) -> dict[str, Any]:
    label = "Approved" if status == "approved" else "Rejected"
    return {"inline_keyboard": [[{"text": label, "callback_data": f"p1a:noop:{status}"}]]}


def send_daily_batch(config: Config, state: dict[str, Any], telegram: TelegramClient, force: bool = False) -> None:
    now = datetime.now(ZoneInfo(config.timezone))
    today = now.date().isoformat()
    if not force and today in set(state.get("sent_dates") or []):
        return
    angels = select_daily_angels(config, state)
    telegram.send_message(config.chat_id, f"P1 daily angel queue: {len(angels)} angels for {today}", config.message_thread_id)
    state.setdefault("angels", {})
    for index, angel in enumerate(angels, start=1):
        state["angels"][angel["id"]] = angel
        sent = telegram.send_message(config.chat_id, angel_message(index, angel), config.message_thread_id, buttons(angel["id"]))
        if isinstance(sent, dict) and sent.get("message_id"):
            state["angels"][angel["id"]]["telegram_message_id"] = sent["message_id"]
    if not force:
        state.setdefault("sent_dates", []).append(today)
    save_state(config, state)


def send_now(config: Config, count: int) -> None:
    send_config = replace(config, batch_size=count)
    telegram = TelegramClient(send_config.telegram_token)
    state = load_state(send_config)
    send_daily_batch(send_config, state, telegram, force=True)
    today = datetime.now(ZoneInfo(send_config.timezone)).date().isoformat()
    if today not in set(state.get("sent_dates") or []):
        state.setdefault("sent_dates", []).append(today)
    save_state(send_config, state)


def append_tsv(path: Path, fields: list[str], row: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    exists = path.exists()
    with path.open("a", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, delimiter="\t", lineterminator="\n")
        if not exists:
            writer.writeheader()
        writer.writerow(row)


def approve_angel(config: Config, angel: dict[str, Any]) -> str:
    row = {
        "Date Added": datetime.now(ZoneInfo(config.timezone)).date().isoformat(),
        "Name": angel.get("name", ""),
        "LinkedIn": angel.get("linkedin_url", ""),
        "City": angel.get("city", ""),
        "Country": angel.get("country", ""),
        "Headline": angel.get("headline", ""),
        "P1 Score": angel.get("triage", {}).get("score", ""),
        "P1 Status": angel.get("triage", {}).get("status", ""),
        "Verdict": "approve",
        "P1 Reasoning": angel.get("triage", {}).get("reasoning", ""),
        "Source": angel.get("source", ""),
    }
    append_tsv(config.out_dir / "p1_approved_angels.tsv", APPROVED_FIELDS, row)
    if not has_google_credentials(config):
        return "Approved locally. Google credentials are not configured yet."
    try:
        if config.google_sheet_id:
            append_google_sheet(config, row, config.google_sheet_id)
            return f"Approved and appended to fixed Google Sheet: {config.google_sheet_tab}."
        if config.drive_folder_id:
            spreadsheet_id = ensure_drive_spreadsheet(config)
            append_google_sheet(config, row, spreadsheet_id)
            return f"Approved and written to Google Drive file: {config.drive_file_name}."
        return "Approved locally. Google destination is not configured yet."
    except Exception as exc:
        append_tsv(
            config.out_dir / "p1_sheet_write_errors.tsv",
            ["time", "name", "error"],
            {"time": datetime.utcnow().isoformat(), "name": row["Name"], "error": str(exc)[:500]},
        )
        return "Approved locally, but Google write failed. Saved to error log."


def append_google_sheet(config: Config, row: dict[str, Any], spreadsheet_id: str) -> None:
    token = google_access_token(
        config,
        ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive.file"],
    )
    tab = config.google_sheet_tab
    ensure_google_sheet_tab(spreadsheet_id, tab, token)
    ensure_google_sheet_headers(spreadsheet_id, tab, token)
    encoded_range = urllib.parse.quote(f"{tab}!A:K", safe="")
    values = [[row[field] for field in APPROVED_FIELDS]]
    google_request_json(
        "POST",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_range}:append?valueInputOption=RAW&insertDataOption=INSERT_ROWS",
        token,
        {"values": values},
    )


def ensure_drive_spreadsheet(config: Config) -> str:
    token = google_access_token(
        config,
        ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/spreadsheets"],
    )
    escaped_name = config.drive_file_name.replace("\\", "\\\\").replace("'", "\\'")
    query = (
        f"'{config.drive_folder_id}' in parents and "
        f"name = '{escaped_name}' and "
        "mimeType = 'application/vnd.google-apps.spreadsheet' and trashed = false"
    )
    search_url = "https://www.googleapis.com/drive/v3/files?" + urllib.parse.urlencode(
        {"q": query, "fields": "files(id,name)", "pageSize": "10", "supportsAllDrives": "true"}
    )
    result = google_request_json("GET", search_url, token)
    files = result.get("files") if isinstance(result, dict) else []
    if isinstance(files, list) and files:
        return str(files[0]["id"])
    created = google_request_json(
        "POST",
        "https://www.googleapis.com/drive/v3/files?fields=id&supportsAllDrives=true",
        token,
        {
            "name": config.drive_file_name,
            "mimeType": "application/vnd.google-apps.spreadsheet",
            "parents": [config.drive_folder_id],
        },
    )
    return str(created["id"])


def ensure_google_sheet_tab(spreadsheet_id: str, tab_name: str, token: str) -> None:
    metadata = google_request_json(
        "GET",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}?fields=sheets.properties",
        token,
    )
    sheets = metadata.get("sheets", []) if isinstance(metadata, dict) else []
    existing = {str(item.get("properties", {}).get("title") or "") for item in sheets if isinstance(item, dict)}
    if tab_name in existing:
        return
    google_request_json(
        "POST",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}:batchUpdate",
        token,
        {"requests": [{"addSheet": {"properties": {"title": tab_name}}}]},
    )


def ensure_google_sheet_headers(spreadsheet_id: str, tab_name: str, token: str) -> None:
    encoded_row = urllib.parse.quote(f"{tab_name}!1:1", safe="")
    existing = google_request_json("GET", f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_row}", token)
    values = existing.get("values") if isinstance(existing, dict) else []
    if values:
        return
    google_request_json(
        "PUT",
        f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{encoded_row}?valueInputOption=RAW",
        token,
        {"values": [APPROVED_FIELDS]},
    )


def has_google_credentials(config: Config) -> bool:
    return bool(
        (config.google_sa_path and Path(config.google_sa_path).exists())
        or (config.google_adc_path and Path(config.google_adc_path).exists())
    )


def google_access_token(config: Config, scopes: list[str]) -> str:
    from google.auth.transport.requests import Request as GoogleAuthRequest
    from google.oauth2.credentials import Credentials as UserCredentials
    from google.oauth2.service_account import Credentials

    if config.google_sa_path and Path(config.google_sa_path).exists():
        credentials = Credentials.from_service_account_file(config.google_sa_path, scopes=scopes)
    elif config.google_adc_path and Path(config.google_adc_path).exists():
        credentials = UserCredentials.from_authorized_user_file(config.google_adc_path, scopes=scopes)
    else:
        raise RuntimeError("Google credentials are not configured")
    credentials.refresh(GoogleAuthRequest())
    if not credentials.token:
        raise RuntimeError("Google access token is empty")
    return credentials.token


def google_request_json(method: str, url: str, token: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method=method,
    )
    with urllib.request.urlopen(request, timeout=90) as response:
        text = response.read().decode("utf-8")
    return json.loads(text) if text else {}


def store_reject_comment(config: Config, angel: dict[str, Any], comment: str, user: dict[str, Any]) -> None:
    path = config.state_dir / "reject_feedback.jsonl"
    item = {
        "time": datetime.utcnow().isoformat(),
        "angel_id": angel.get("id"),
        "name": angel.get("name"),
        "linkedin_url": angel.get("linkedin_url"),
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
    if len(parts) != 3 or parts[0] != "p1a":
        return
    action, sid = parts[1], parts[2]
    if action == "noop":
        telegram.answer_callback(callback_id, "Already handled.")
        return
    angel = state.get("angels", {}).get(sid)
    if not isinstance(angel, dict):
        telegram.answer_callback(callback_id, "Angel not found in state.")
        return
    decisions = state.setdefault("decisions", {})
    existing_decision = decisions.get(sid)
    if isinstance(existing_decision, dict):
        status = str(existing_decision.get("status") or "handled")
        telegram.answer_callback(callback_id, f"Already {status}.")
        message_id = callback_message_id(query)
        if message_id:
            try:
                telegram.edit_reply_markup(config.chat_id, message_id, status_button(status))
            except TelegramError as exc:
                print(f"telegram edit warning: {exc}", flush=True)
        return
    if action == "approve":
        message = approve_angel(config, angel)
        decisions[sid] = {"status": "approved", "time": datetime.utcnow().isoformat()}
        telegram.answer_callback(callback_id, "Approved")
        message_id = callback_message_id(query)
        if message_id:
            try:
                telegram.edit_reply_markup(config.chat_id, message_id, status_button("approved"))
            except TelegramError as exc:
                print(f"telegram edit warning: {exc}", flush=True)
        telegram.send_message(config.chat_id, f"{angel.get('name')}: {message}", config.message_thread_id)
        save_state(config, state)
        return
    if action == "reject":
        user = query.get("from") if isinstance(query.get("from"), dict) else {}
        key = str(user.get("id") or "unknown")
        decisions[sid] = {"status": "rejected", "time": datetime.utcnow().isoformat(), "comment_pending": True}
        state.setdefault("pending_reject_comments", {})[key] = sid
        save_state(config, state)
        telegram.answer_callback(callback_id, "Rejected")
        message_id = callback_message_id(query)
        if message_id:
            try:
                telegram.edit_reply_markup(config.chat_id, message_id, status_button("rejected"))
            except TelegramError as exc:
                print(f"telegram edit warning: {exc}", flush=True)
        telegram.send_message(config.chat_id, f"Why reject {angel.get('name')}? Reply with the comment in this thread.", config.message_thread_id)


def callback_message_id(query: dict[str, Any]) -> int | None:
    message = query.get("message") if isinstance(query.get("message"), dict) else {}
    try:
        return int(message.get("message_id"))
    except (TypeError, ValueError):
        return None


def handle_message(config: Config, state: dict[str, Any], telegram: TelegramClient, message: dict[str, Any]) -> None:
    text = str(message.get("text") or "").strip()
    user = message.get("from") if isinstance(message.get("from"), dict) else {}
    user_key = str(user.get("id") or "unknown")
    if user_key in state.get("pending_reject_comments", {}) and text and not text.startswith("/"):
        sid = state["pending_reject_comments"].pop(user_key)
        angel = state.get("angels", {}).get(sid, {})
        if isinstance(angel, dict):
            store_reject_comment(config, angel, text, user)
            decision = state.setdefault("decisions", {}).setdefault(sid, {"status": "rejected"})
            decision["comment"] = text
            decision["comment_pending"] = False
            telegram.send_message(config.chat_id, f"Saved reject feedback for {angel.get('name')}. I will use this in future scoring.", config.message_thread_id)
            save_state(config, state)
        return
    if text in {"/send_today", "/send_today@p1"}:
        send_daily_batch(config, state, telegram, force=True)
    elif text in {"/p1_status", "/p1_status@p1"}:
        telegram.send_message(config.chat_id, status_text(config, state), config.message_thread_id)


def status_text(config: Config, state: dict[str, Any]) -> str:
    approved_path = config.out_dir / "p1_approved_angels.tsv"
    feedback_path = config.state_dir / "reject_feedback.jsonl"
    approved_rows = max(0, len(approved_path.read_text(encoding="utf-8").splitlines()) - 1) if approved_path.exists() else 0
    feedback_rows = len(feedback_path.read_text(encoding="utf-8").splitlines()) if feedback_path.exists() else 0
    return "\n".join(
        [
            "P1 Telegram angel agent",
            f"daily_time: {config.daily_time} {config.timezone}",
            f"batch_size: {config.batch_size}",
            f"approved_local_rows: {approved_rows}",
            f"reject_feedback_rows: {feedback_rows}",
            f"google_drive_configured: {bool(config.drive_folder_id and has_google_credentials(config))}",
            f"google_sheet_configured: {bool(config.google_sheet_id and has_google_credentials(config))}",
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
    while True:
        try:
            if next_daily_due(config, state):
                send_daily_batch(config, state, telegram)
            for update in telegram.get_updates(state.get("offset")):
                state["offset"] = int(update["update_id"]) + 1
                if isinstance(update.get("callback_query"), dict):
                    handle_callback(config, state, telegram, update["callback_query"])
                elif isinstance(update.get("message"), dict):
                    handle_message(config, state, telegram, update["message"])
                save_state(config, state)
        except TelegramError as exc:
            print(f"telegram polling warning: {exc}", flush=True)
            time.sleep(30 if exc.status_code == 409 else 10)
        time.sleep(2)


if __name__ == "__main__":
    if "--send-now" in sys.argv[1:]:
        index = sys.argv.index("--send-now")
        count = int(sys.argv[index + 1]) if len(sys.argv) > index + 1 else 10
        send_now(load_config(), count)
        raise SystemExit(0)
    if any(arg in {"-h", "--help"} for arg in sys.argv[1:]):
        print(
            "\n".join(
                [
                    "P1 Telegram angel agent",
                    "",
                    "Environment:",
                    "  P1_TELEGRAM_ENV_FILE=/opt/p1/.env",
                    "  TELEGRAM_BOT_TOKEN=...",
                    "  TELEGRAM_CHAT_ID=...",
                    "  TELEGRAM_MESSAGE_THREAD_ID=...  # optional p1 topic",
                    "  GEMINI_API_KEY=...",
                    "  P1_ANGEL_DAILY_TIME=10:00",
                    "  P1_ANGEL_TIMEZONE=Asia/Nicosia",
                    "  P1_ANGEL_BATCH_SIZE=30",
                    "",
                    "Telegram commands:",
                    "  /send_today",
                    "  /p1_status",
                ]
            )
        )
        raise SystemExit(0)
    run()
