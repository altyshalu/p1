from __future__ import annotations

import json
from typing import Any

from rich import box
from rich.console import Group, RenderableType
from rich.layout import Layout
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

COMPACT_PAYLOAD_LIMIT = 180
MAX_PIPELINE_ROWS = 7
MAX_DRAFT_CHARS = 420
MAX_WAITING_CHARS = 520
MAX_EVENT_ROWS = 4


def render_run_snapshot(run: dict[str, Any], show_full_events: bool = False, height: int | None = None) -> RenderableType:
    if height is not None:
        return _render_fullscreen(run, show_full_events, height)
    return _render_group(run, show_full_events)


def _render_fullscreen(run: dict[str, Any], show_full_events: bool, height: int) -> Layout:
    layout = Layout()
    waiting_height = 0 if _waiting_user_panel(run) is None else 8
    events_height = max(7, 14 if show_full_events else 9)
    draft_height = 7
    eval_height = 4
    header_height = 7
    footer_height = 3
    reserved = header_height + waiting_height + events_height + draft_height + eval_height + footer_height
    pipeline_height = max(6, height - reserved)
    layout.split_column(
        Layout(_header(run), name="header", size=header_height),
        Layout(_tasks_table(run, max_rows=max(1, pipeline_height - 4)), name="pipeline", size=pipeline_height),
        Layout(_evals_table(run), name="evals", size=eval_height),
        Layout(_draft_panel(run, max_chars=MAX_DRAFT_CHARS), name="draft", size=draft_height),
        Layout(_waiting_user_panel(run) or "", name="waiting", size=waiting_height),
        Layout(_events_table(run, show_full_events, max_rows=MAX_EVENT_ROWS), name="events", size=events_height),
        Layout(_footer(show_full_events), name="footer", size=footer_height),
    )
    return layout


def _render_group(run: dict[str, Any], show_full_events: bool = False) -> Group:
    blocks = [_header(run), _tasks_table(run), _evals_table(run), _draft_panel(run)]
    waiting_panel = _waiting_user_panel(run)
    if waiting_panel is not None:
        blocks.append(waiting_panel)
    blocks.extend([_events_table(run, show_full_events), _footer(show_full_events)])
    return Group(*blocks)


def _header(run: dict[str, Any]) -> Panel:
    header = Panel(
        Text.from_markup(
            f"[bold]ABRT Live Run[/bold]\n"
            f"Process: [cyan]{run['process_key']}[/cyan]\n"
            f"Run: [dim]{run['id']}[/dim]\n"
            f"Status: [{_status_style(run['status'])}]{run['status']}[/{_status_style(run['status'])}]\n"
            f"Goal: {run['goal']}"
        ),
        title="L2/L3 Runtime",
        border_style=_status_style(run["status"]),
    )
    return header


def _footer(show_full_events: bool) -> Panel:
    return Panel(
        Text.from_markup(
            "[bold cyan]f[/bold cyan] full events   "
            "[bold cyan]q[/bold cyan] quit   "
            "[bold cyan]watch[/bold cyan] auto-refresh   "
            f"events: [{'bold green' if show_full_events else 'dim'}]"
            f"{'full' if show_full_events else 'compact'}"
            f"[/{'bold green' if show_full_events else 'dim'}]"
        ),
        border_style="dim",
    )


def _tasks_table(run: dict[str, Any], max_rows: int | None = None) -> Table:
    table = Table(title="Pipeline", title_style="bold", box=box.SIMPLE_HEAVY)
    table.add_column("State", no_wrap=True, style="bold")
    table.add_column("Worker", style="cyan")
    table.add_column("Task", style="bold")
    table.add_column("Goal", style="white")
    tasks = run.get("tasks", [])
    visible_tasks = tasks[-max_rows:] if max_rows is not None and len(tasks) > max_rows else tasks
    hidden_count = len(tasks) - len(visible_tasks)
    if hidden_count:
        table.add_row("[dim]…[/dim]", "[dim]earlier[/dim]", "[dim]hidden[/dim]", f"[dim]{hidden_count} earlier task(s) hidden[/dim]")
    for task in visible_tasks:
        table.add_row(_state_icon(task["status"]), task["worker_profile"], task["task_type"], task.get("goal", ""))
    return table


def _evals_table(run: dict[str, Any]) -> Table:
    table = Table(title="Evals", title_style="bold", box=box.SIMPLE)
    table.add_column("Eval", style="cyan")
    table.add_column("Passed")
    table.add_column("Score", justify="right")
    table.add_column("Threshold", justify="right")
    for item in run.get("evals", []):
        passed = bool(item["passed"])
        table.add_row(
            item.get("eval_key") or "unknown",
            "[green]yes[/green]" if passed else "[red]no[/red]",
            str(item["score"]),
            str(item.get("threshold")),
        )
    return table


def _draft_panel(run: dict[str, Any], max_chars: int | None = None) -> Panel:
    drafts = []
    for artifact in run.get("artifacts", []):
        payload = artifact.get("payload", {})
        drafts.extend(payload.get("edited_drafts", []))
        drafts.extend(payload.get("drafts", []))
    if not drafts:
        return Panel("[dim]No drafts yet.[/dim]", title="Draft Preview", border_style="dim")
    lines = []
    for draft in drafts[-2:]:
        text = draft.get("text")
        if not text and isinstance(draft.get("thread"), list):
            text = "\n".join(str(item) for item in draft["thread"])
        lines.append(f"[bold]{draft.get('channel', 'unknown')}[/bold] · {draft.get('status', 'draft')}\n{text or '[dim]No text field yet.[/dim]'}")
    content = "\n\n".join(lines)
    return Panel(_clip(content, max_chars), title="Draft Preview", border_style="green")


def _waiting_user_panel(run: dict[str, Any]) -> Panel | None:
    if run.get("status") != "waiting_user":
        return None
    message = _latest_event_payload(run, "l2_message_user").get("message") or run.get("output", {}).get("requested_edit")
    if not message:
        return None
    body = Text.from_markup(
        "[bold magenta]L2 is asking for your input[/bold magenta]\n\n"
        f"{_clip(str(message), MAX_WAITING_CHARS)}\n\n"
        "[dim]Type your answer in the prompt below. The watcher will resume this same run automatically.[/dim]"
    )
    return Panel(body, title="User Input Required", border_style="magenta")


def _events_table(run: dict[str, Any], show_full_events: bool = False, max_rows: int | None = None) -> Table:
    table = Table(title="Recent Events", title_style="bold", box=box.ROUNDED, show_lines=show_full_events)
    table.add_column("Event", style="bold magenta", no_wrap=True)
    table.add_column("Payload", overflow="fold")
    events = run.get("events", [])
    visible_events = events[-(max_rows or 5) :]
    for event in visible_events:
        table.add_row(event["event_type"], Text(_format_payload(event.get("payload", {}), show_full_events), style="dim"))
    return table


def _format_payload(payload: Any, show_full: bool) -> str:
    if show_full:
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    compact = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ": "))
    if len(compact) <= COMPACT_PAYLOAD_LIMIT:
        return compact
    return f"{compact[: COMPACT_PAYLOAD_LIMIT - 3]}..."


def _clip(value: str, max_chars: int | None) -> str:
    if max_chars is None or len(value) <= max_chars:
        return value
    return f"{value[: max_chars - 3]}..."


def _latest_event_payload(run: dict[str, Any], event_type: str) -> dict[str, Any]:
    for event in reversed(run.get("events", [])):
        if event.get("event_type") == event_type:
            payload = event.get("payload", {})
            return payload if isinstance(payload, dict) else {}
    return {}


def _state_icon(status: str) -> str:
    return {
        "completed": "[green]✓[/green]",
        "running": "[yellow]…[/yellow]",
        "failed": "[red]×[/red]",
        "waiting_approval": "[cyan]?[/cyan]",
    }.get(status, "[dim]·[/dim]")


def _status_style(status: str) -> str:
    return {
        "completed": "green",
        "running": "yellow",
        "failed": "red",
        "waiting_approval": "cyan",
        "waiting_user": "magenta",
    }.get(status, "white")
