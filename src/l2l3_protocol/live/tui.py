from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
from typing import Any

from rich.panel import Panel
from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Input, Label, RichLog, Static
from textual import work
from textual.worker import Worker, WorkerState

from l2l3_protocol.live.client import LiveApiClient


TERMINAL_STATUSES = {"completed", "failed", "cancelled"}
COMPACT_PAYLOAD_LIMIT = 360


@dataclass(frozen=True)
class ApprovalCommand:
    action: str
    payload: dict[str, Any]


def parse_approval_command(value: str) -> ApprovalCommand:
    command = value.strip()
    lowered = command.lower()
    if lowered in {"approve", "approved", "yes", "y"}:
        return ApprovalCommand(action="approve", payload={})
    if lowered.startswith("reject"):
        reason = command[len("reject") :].strip(" :-")
        if not reason:
            raise ValueError("Use: reject <reason>")
        return ApprovalCommand(action="reject", payload={"reason": reason})
    if lowered.startswith("edit"):
        message = command[len("edit") :].strip(" :-")
        if not message:
            raise ValueError("Use: edit <message>")
        return ApprovalCommand(action="request_edit", payload={"message": message})
    raise ValueError("Waiting for approval command: approve | reject <reason> | edit <message>")


class LiveRunApp(App[None]):
    CSS = """
    Screen {
        background: #071111;
        color: #dce8df;
        layout: vertical;
    }

    Header {
        background: #102421;
        color: #dff8eb;
        text-style: bold;
    }

    Footer {
        background: #102421;
        color: #b9d5c8;
    }

    #status {
        height: 7;
        margin: 1 1 0 1;
        padding: 0 1;
        border: round #48d597;
        background: #0d1a18;
    }

    #main {
        height: 1fr;
        margin: 1;
    }

    #left {
        width: 47%;
        min-width: 48;
        height: 100%;
    }

    #right {
        width: 1fr;
        height: 100%;
        margin-left: 1;
    }

    .section-title {
        height: 1;
        color: #8ce7ba;
        text-style: bold;
    }

    #tasks {
        height: 3fr;
        border: round #2a7560;
        background: #091615;
    }

    #evals {
        height: 1fr;
        min-height: 6;
        border: round #2a7560;
        background: #091615;
    }

    #prompt {
        height: 8;
        border: round #d48cff;
        padding: 0 1;
        background: #160f1d;
    }

    #drafts {
        height: 2fr;
        min-height: 8;
        border: round #3aa675;
        padding: 0 1;
        background: #081513;
    }

    #events {
        height: 2fr;
        min-height: 8;
        border: round #355a71;
        padding: 0 1;
        background: #081219;
    }

    #command {
        height: 3;
        margin: 0 1 1 1;
        border: tall #48d597;
        background: #081513;
    }

    #command:disabled {
        border: tall #314643;
        color: #6b8178;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
        Binding("f", "toggle_events", "Full events"),
    ]

    def __init__(self, *, api_url: str, run_id: str) -> None:
        super().__init__()
        self.api_url = api_url
        self.run_id = run_id
        self.client = LiveApiClient(api_url)
        self.run: dict[str, Any] | None = None
        self.show_full_events = False
        self._polling_enabled = True

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        yield Static(id="status")
        with Horizontal(id="main"):
            with Vertical(id="left"):
                yield Label("Pipeline", classes="section-title")
                yield DataTable(id="tasks", zebra_stripes=True, cursor_type="row")
                yield Label("Evals", classes="section-title")
                yield DataTable(id="evals", zebra_stripes=True, cursor_type="row")
            with Vertical(id="right"):
                yield Static(id="prompt")
                yield Label("Draft Preview", classes="section-title")
                yield RichLog(id="drafts", wrap=True, markup=True, highlight=True)
                yield Label("Recent Events", classes="section-title")
                yield RichLog(id="events", wrap=True, markup=True, highlight=True)
        yield Input(id="command")
        yield Footer()

    def on_mount(self) -> None:
        self.title = "ABRT L2/L3 Runtime"
        self.sub_title = self.run_id
        self._setup_tables()
        self.fetch_run()
        self.set_interval(1.0, self._poll)

    def _setup_tables(self) -> None:
        tasks = self.query_one("#tasks", DataTable)
        tasks.add_columns("State", "Worker", "Task", "Goal")
        evals = self.query_one("#evals", DataTable)
        evals.add_columns("Eval", "Passed", "Score", "Threshold")

    def _poll(self) -> None:
        if self._polling_enabled:
            self.fetch_run()

    def action_refresh(self) -> None:
        self.fetch_run()

    def action_toggle_events(self) -> None:
        self.show_full_events = not self.show_full_events
        if self.run is not None:
            self._render(self.run)

    @work(exclusive=True)
    async def fetch_run(self) -> dict[str, Any]:
        return await self.client.get_run(self.run_id)

    @work(exclusive=True)
    async def send_user_message(self, message: str) -> dict[str, Any]:
        return await self.client.send_message(self.run_id, message)

    @work(exclusive=True)
    async def send_approval_control(self, command: ApprovalCommand) -> dict[str, Any]:
        return await self.client.control(self.run_id, command.action, command.payload)

    def on_worker_state_changed(self, event: Worker.StateChanged) -> None:
        if event.state == WorkerState.SUCCESS and isinstance(event.worker.result, dict):
            self.run = event.worker.result
            self._render(event.worker.result)
        elif event.state == WorkerState.ERROR:
            self._show_error(f"{type(event.worker.error).__name__}: {event.worker.error}")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if self.run is None:
            return
        value = event.value.strip()
        if not value:
            return
        command_input = self.query_one("#command", Input)
        command_input.value = ""
        command_input.disabled = True
        if self.run.get("status") == "waiting_user":
            self.send_user_message(value)
            return
        if self.run.get("status") == "waiting_approval":
            try:
                command = parse_approval_command(value)
            except ValueError as exc:
                self._show_error(str(exc))
                command_input.disabled = False
                command_input.focus()
                return
            self.send_approval_control(command)

    def _render(self, run: dict[str, Any]) -> None:
        self._polling_enabled = run.get("status") not in TERMINAL_STATUSES
        self._render_status(run)
        self._render_tasks(run)
        self._render_evals(run)
        self._render_prompt(run)
        self._render_drafts(run)
        self._render_events(run)
        self._render_command(run)

    def _render_status(self, run: dict[str, Any]) -> None:
        status = str(run.get("status", "unknown"))
        status_text = Text(status, style=_status_style(status))
        updated_at = _format_timestamp(run.get("updated_at"))
        counts = f"{len(run.get('tasks', []))} tasks · {len(run.get('evals', []))} evals · {len(run.get('events', []))} events"
        body = Text.assemble(
            ("ABRT Live Run\n", "bold #dff8eb"),
            ("Process: ", "bold"),
            (str(run.get("process_key", "unknown")), "#8ce7ba"),
            "\n",
            ("Run: ", "bold"),
            (str(run.get("id", self.run_id)), "dim"),
            "\n",
            ("Status: ", "bold"),
            status_text,
            ("   Updated: ", "bold"),
            (updated_at, "dim"),
            ("   ", ""),
            (counts, "#9cc7ba"),
            "\n",
            ("Goal: ", "bold"),
            str(run.get("goal", "")),
        )
        self.query_one("#status", Static).update(body)

    def _render_tasks(self, run: dict[str, Any]) -> None:
        table = self.query_one("#tasks", DataTable)
        table.clear()
        for task in run.get("tasks", []):
            status = str(task.get("status", "unknown"))
            table.add_row(
                _state_text(status),
                str(task.get("worker_profile", "")),
                str(task.get("task_type", "")),
                str(task.get("goal", "")),
            )

    def _render_evals(self, run: dict[str, Any]) -> None:
        table = self.query_one("#evals", DataTable)
        table.clear()
        for item in run.get("evals", []):
            passed = bool(item.get("passed"))
            table.add_row(
                str(item.get("eval_key") or "unknown"),
                Text("yes" if passed else "no", style="bold green" if passed else "bold red"),
                str(item.get("score", "")),
                str(item.get("threshold", "")),
            )

    def _render_prompt(self, run: dict[str, Any]) -> None:
        status = run.get("status")
        prompt = self.query_one("#prompt", Static)
        if status == "waiting_user":
            message = _latest_event_payload(run, "l2_message_user").get("message") or run.get("output", {}).get("requested_edit")
            body = Text.assemble(
                ("L2 needs your answer\n", "bold #ffb3ff"),
                (str(message or "No message payload found."), "#f3dcff"),
                ("\n\nType below and press Enter. The same run resumes immediately.", "dim"),
            )
            prompt.update(body)
            return
        if status == "waiting_approval":
            body = Text.assemble(
                ("Human approval gate\n", "bold #ffdc8c"),
                ("Commands: ", "bold"),
                ("approve", "green"),
                (" · ", "dim"),
                ("reject <reason>", "red"),
                (" · ", "dim"),
                ("edit <message>", "cyan"),
                ("\nThe run stays paused until you choose.", "dim"),
            )
            prompt.update(body)
            return
        prompt.update(Text.assemble(("Runtime is running.\n", "bold #8ce7ba"), ("No user input required right now.", "dim")))

    def _render_drafts(self, run: dict[str, Any]) -> None:
        log = self.query_one("#drafts", RichLog)
        log.clear()
        drafts = _collect_drafts(run)
        if not drafts:
            log.write(Text("No drafts yet.", style="dim"))
            return
        for index, draft in enumerate(drafts[-4:], start=max(1, len(drafts) - 3)):
            text = _draft_text(draft)
            title = f"{draft.get('channel', 'unknown')} · {draft.get('status', 'draft')} · draft {index}"
            log.write(Panel(text or "[dim]No draft text yet.[/dim]", title=title, border_style="green"))

    def _render_events(self, run: dict[str, Any]) -> None:
        log = self.query_one("#events", RichLog)
        log.clear()
        events = run.get("events", [])
        if not events:
            log.write(Text("No events yet.", style="dim"))
            return
        visible_events = events if self.show_full_events else events[-12:]
        if not self.show_full_events and len(events) > len(visible_events):
            log.write(Text(f"{len(events) - len(visible_events)} earlier events hidden. Press f for full event history.", style="dim"))
        for event in visible_events:
            event_type = str(event.get("event_type", "unknown"))
            created = _format_timestamp(event.get("created_at"))
            payload = event.get("payload", {})
            log.write(Text.assemble((event_type, "bold magenta"), ("  "), (created, "dim")))
            if self.show_full_events:
                log.write(Syntax(json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True), "json", word_wrap=True))
            else:
                log.write(Text(_compact_payload(payload), style="dim"))

    def _render_command(self, run: dict[str, Any]) -> None:
        command = self.query_one("#command", Input)
        status = run.get("status")
        waiting = status in {"waiting_user", "waiting_approval"}
        command.disabled = not waiting
        if status == "waiting_user":
            command.placeholder = "Answer L2 here and press Enter"
            command.focus()
        elif status == "waiting_approval":
            command.placeholder = "approve | reject <reason> | edit <message>"
            command.focus()
        elif status in TERMINAL_STATUSES:
            command.placeholder = f"Run is {status}. Press q to quit."
        else:
            command.placeholder = "Watching live. Press f for full events, r to refresh, q to quit."

    def _show_error(self, message: str) -> None:
        prompt = self.query_one("#prompt", Static)
        prompt.update(Text.assemble(("TUI action failed\n", "bold red"), (message, "red")))


def _collect_drafts(run: dict[str, Any]) -> list[dict[str, Any]]:
    drafts: list[dict[str, Any]] = []
    for artifact in run.get("artifacts", []):
        payload = artifact.get("payload", {})
        if isinstance(payload, dict):
            drafts.extend(item for item in payload.get("edited_drafts", []) if isinstance(item, dict))
            drafts.extend(item for item in payload.get("drafts", []) if isinstance(item, dict))
    return drafts


def _draft_text(draft: dict[str, Any]) -> str:
    text = draft.get("text")
    if isinstance(text, str):
        return text
    thread = draft.get("thread")
    if isinstance(thread, list):
        return "\n\n".join(str(item) for item in thread)
    return ""


def _latest_event_payload(run: dict[str, Any], event_type: str) -> dict[str, Any]:
    for event in reversed(run.get("events", [])):
        if event.get("event_type") == event_type:
            payload = event.get("payload", {})
            return payload if isinstance(payload, dict) else {}
    return {}


def _compact_payload(payload: Any) -> str:
    compact = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ": "))
    if len(compact) <= COMPACT_PAYLOAD_LIMIT:
        return compact
    return f"{compact[: COMPACT_PAYLOAD_LIMIT - 3]}..."


def _format_timestamp(value: Any) -> str:
    if not value:
        return "unknown"
    try:
        return datetime.fromisoformat(str(value)).strftime("%H:%M:%S")
    except ValueError:
        return str(value)


def _state_text(status: str) -> Text:
    labels = {
        "completed": ("ok", "bold green"),
        "running": ("run", "bold yellow"),
        "failed": ("fail", "bold red"),
        "waiting_approval": ("gate", "bold cyan"),
        "waiting_user": ("ask", "bold magenta"),
    }
    label, style = labels.get(status, ("wait", "dim"))
    return Text(label, style=style)


def _status_style(status: str) -> str:
    return {
        "completed": "bold green",
        "running": "bold yellow",
        "failed": "bold red",
        "cancelled": "bold red",
        "waiting_approval": "bold cyan",
        "waiting_user": "bold magenta",
    }.get(status, "white")
