from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import Any

import httpx

from l2l3_protocol.services.p1_defaults import DEFAULT_P1_GOAL, P1_PLAYBOOK_KEY, default_p1_inputs


@dataclass(frozen=True)
class TelegramConfig:
    token: str
    allowed_chat_ids: set[int]
    api_base_url: str = "http://127.0.0.1:8000"
    operator_api_key: str | None = None
    poll_timeout_seconds: int = 30


class TelegramControlError(RuntimeError):
    pass


def load_config_from_env() -> TelegramConfig:
    token = _required_env("TELEGRAM_BOT_TOKEN")
    allowed_raw = _required_env("TELEGRAM_ALLOWED_CHAT_IDS")
    allowed = {int(item.strip()) for item in allowed_raw.split(",") if item.strip()}
    if not allowed:
        raise TelegramControlError("TELEGRAM_ALLOWED_CHAT_IDS must contain at least one chat id")
    return TelegramConfig(
        token=token,
        allowed_chat_ids=allowed,
        api_base_url=os.environ.get("L2L3_API_BASE_URL", "http://127.0.0.1:8000").rstrip("/"),
        operator_api_key=os.environ.get("L2L3_OPERATOR_API_KEY"),
    )


def _required_env(key: str) -> str:
    value = os.environ.get(key)
    if not value or not value.strip():
        raise TelegramControlError(f"missing required environment variable: {key}")
    return value.strip()


def parse_command(text: str) -> tuple[str, str]:
    stripped = text.strip()
    if not stripped:
        return "", ""
    first, _, rest = stripped.partition(" ")
    command = first.split("@", 1)[0].lower()
    return command, rest.strip()


def is_allowed_chat(chat_id: int, allowed_chat_ids: set[int]) -> bool:
    return chat_id in allowed_chat_ids


class L2L3ApiClient:
    def __init__(self, base_url: str, client: httpx.Client | None = None, operator_api_key: str | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client(timeout=120)
        self.operator_api_key = operator_api_key

    def health(self) -> dict[str, Any]:
        return self._request("GET", "/health")

    def create_p1_run(self) -> dict[str, Any]:
        return self._request(
            "POST",
            "/runs",
            json={
                "playbook_key": P1_PLAYBOOK_KEY,
                "goal": DEFAULT_P1_GOAL,
                "require_human_approval": True,
                "inputs": default_p1_inputs(),
            },
        )

    def latest_p1_run(self) -> dict[str, Any] | None:
        runs = self._request("GET", f"/runs?playbook_key={P1_PLAYBOOK_KEY}&limit=1")
        if not isinstance(runs, list):
            raise TelegramControlError("GET /runs returned non-list payload")
        return runs[0] if runs else None

    def get_run(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}")

    def get_summary(self, run_id: str) -> dict[str, Any]:
        return self._request("GET", f"/runs/{run_id}/summary")

    def approve(self, run_id: str) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/control", json={"action": "approve", "payload": {}})

    def reject(self, run_id: str, reason: str) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/control", json={"action": "reject", "payload": {"reason": reason}})

    def request_edit(self, run_id: str, message: str) -> dict[str, Any]:
        return self._request("POST", f"/runs/{run_id}/messages", json={"message": message})

    def _request(self, method: str, path: str, json: dict[str, Any] | None = None) -> Any:
        headers = {"authorization": f"Bearer {self.operator_api_key}"} if self.operator_api_key else None
        response = self.client.request(method, f"{self.base_url}{path}", json=json, headers=headers)
        if response.status_code >= 400:
            raise TelegramControlError(f"{method} {path} failed: HTTP {response.status_code} {response.text[:500]}")
        return response.json()


class TelegramApiClient:
    def __init__(self, token: str, client: httpx.Client | None = None) -> None:
        self.base_url = f"https://api.telegram.org/bot{token}"
        self.client = client or httpx.Client(timeout=120)

    def get_updates(self, offset: int | None, timeout_seconds: int) -> list[dict[str, Any]]:
        payload: dict[str, Any] = {"timeout": timeout_seconds, "allowed_updates": ["message"]}
        if offset is not None:
            payload["offset"] = offset
        result = self._request("getUpdates", payload)
        if not isinstance(result, list):
            raise TelegramControlError("Telegram getUpdates returned non-list result")
        return result

    def send_message(self, chat_id: int, text: str) -> None:
        for chunk in _telegram_chunks(text):
            self._request("sendMessage", {"chat_id": chat_id, "text": chunk, "disable_web_page_preview": True})

    def _request(self, method: str, payload: dict[str, Any]) -> Any:
        response = self.client.post(f"{self.base_url}/{method}", json=payload)
        if response.status_code >= 400:
            raise TelegramControlError(f"Telegram {method} failed: HTTP {response.status_code} {response.text[:500]}")
        data = response.json()
        if data.get("ok") is not True:
            raise TelegramControlError(f"Telegram {method} returned ok=false: {data}")
        return data.get("result")


def _telegram_chunks(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    chunks: list[str] = []
    remaining = text
    while remaining:
        chunks.append(remaining[:limit])
        remaining = remaining[limit:]
    return chunks


class TelegramControlBot:
    def __init__(self, config: TelegramConfig, api: L2L3ApiClient | None = None, telegram: TelegramApiClient | None = None) -> None:
        self.config = config
        self.api = api or L2L3ApiClient(config.api_base_url, operator_api_key=config.operator_api_key)
        self.telegram = telegram or TelegramApiClient(config.token)

    def run_forever(self) -> None:
        self.api.health()
        offset: int | None = None
        while True:
            try:
                updates = self.telegram.get_updates(offset, self.config.poll_timeout_seconds)
                for update in updates:
                    offset = int(update["update_id"]) + 1
                    self._handle_update(update)
            except TelegramControlError as exc:
                print(f"telegram_control_error: {exc}", flush=True)
                time.sleep(5)

    def _handle_update(self, update: dict[str, Any]) -> None:
        message = update.get("message") if isinstance(update.get("message"), dict) else {}
        chat = message.get("chat") if isinstance(message.get("chat"), dict) else {}
        chat_id = int(chat.get("id") or 0)
        text = str(message.get("text") or "")
        if not is_allowed_chat(chat_id, self.config.allowed_chat_ids):
            if chat_id:
                self.telegram.send_message(chat_id, "Access denied.")
            return
        try:
            reply = self.handle_text(text)
        except TelegramControlError as exc:
            reply = f"Error: {exc}"
        self.telegram.send_message(chat_id, reply)

    def handle_text(self, text: str) -> str:
        command, rest = parse_command(text)
        if command in {"/start", "/help"}:
            return help_message()
        if command == "/p1":
            created = self.api.create_p1_run()
            return f"Started P1 run.\nrun_id: {created.get('id')}\nstatus: {created.get('status')}"
        if command in {"/latest", "/status"}:
            run_id = rest or self._latest_run_id()
            return format_summary(self.api.get_summary(run_id))
        if command == "/metrics":
            run_id = rest or self._latest_run_id()
            return format_metrics(self.api.get_summary(run_id))
        if command == "/drafts":
            run_id = rest or self._latest_run_id()
            return format_drafts(self.api.get_run(run_id))
        if command == "/approve":
            run_id = rest or self._latest_run_id()
            result = self.api.approve(run_id)
            return f"Approved run.\nrun_id: {run_id}\nstatus: {result.get('status')}"
        if command == "/reject":
            run_id, reason = _split_run_and_message(rest)
            result = self.api.reject(run_id or self._latest_run_id(), reason or "Rejected from Telegram control.")
            return f"Rejected run.\nstatus: {result.get('status')}"
        if command == "/edit":
            run_id, message = _split_run_and_message(rest)
            if not message:
                raise TelegramControlError("/edit requires feedback text")
            result = self.api.request_edit(run_id or self._latest_run_id(), message)
            return f"Sent edit request.\nstatus: {result.get('status')}"
        return help_message()

    def _latest_run_id(self) -> str:
        run = self.api.latest_p1_run()
        if run is None:
            raise TelegramControlError("no P1 runs found")
        run_id = str(run.get("id") or "")
        if not run_id:
            raise TelegramControlError("latest P1 run has no id")
        return run_id


def _split_run_and_message(rest: str) -> tuple[str, str]:
    first, _, message = rest.partition(" ")
    if first.startswith("run_") or len(first) >= 32:
        return first, message.strip()
    return "", rest.strip()


def help_message() -> str:
    return "\n".join(
        [
            "ABRT P1 control",
            "/p1 - start a real P1 run",
            "/latest - show latest P1 run",
            "/status [run_id] - show run status",
            "/metrics [run_id] - show funnel metrics",
            "/drafts [run_id] - show outreach drafts",
            "/approve [run_id] - approve pending internal writes",
            "/reject [run_id] reason - reject run",
            "/edit [run_id] feedback - send operator feedback",
        ]
    )


def format_summary(summary: dict[str, Any]) -> str:
    pending = summary.get("pending_actions") if isinstance(summary.get("pending_actions"), list) else []
    diagnosis = summary.get("latest_diagnosis") if isinstance(summary.get("latest_diagnosis"), dict) else {}
    return "\n".join(
        [
            f"run_id: {summary.get('id')}",
            f"status: {summary.get('status')}",
            f"playbook: {summary.get('playbook_key')}",
            f"goal: {summary.get('goal')}",
            f"pending: {len(pending)}",
            f"diagnosis: {diagnosis.get('root_cause') or 'none'}",
        ]
    )


def format_metrics(summary: dict[str, Any]) -> str:
    metrics = summary.get("latest_metrics") if isinstance(summary.get("latest_metrics"), dict) else {}
    if not metrics:
        return "No metrics yet."
    keys = [
        "raw_leads",
        "normalized_leads",
        "rejected_leads",
        "triage_qualified",
        "dossiers",
        "gateway_approved",
        "gateway_rejected",
        "drafted",
        "eval_passed",
        "sheet_written",
        "data_lake_written",
        "outreach_master_written",
        "provider_cache_hits",
    ]
    return "\n".join(f"{key}: {metrics.get(key, 0)}" for key in keys)


def format_drafts(run: dict[str, Any]) -> str:
    output = run.get("output") if isinstance(run.get("output"), dict) else {}
    package = output.get("approval_package") if isinstance(output.get("approval_package"), dict) else {}
    drafts = package.get("outreach_drafts") if isinstance(package.get("outreach_drafts"), list) else []
    if not drafts:
        return "No outreach drafts yet."
    lines = ["Outreach drafts:"]
    for item in drafts[:5]:
        if not isinstance(item, dict):
            continue
        lines.append(f"\n{item.get('name')} | {item.get('current_role')}")
        lines.append(str(item.get("text") or "").strip())
    if len(drafts) > 5:
        lines.append(f"\n...and {len(drafts) - 5} more")
    return "\n".join(lines)


def main() -> None:
    TelegramControlBot(load_config_from_env()).run_forever()


if __name__ == "__main__":
    main()
