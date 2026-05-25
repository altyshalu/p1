from __future__ import annotations

import json
from typing import Any

from rich import box
from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text

COMPACT_PAYLOAD_LIMIT = 180


def render_run_snapshot(run: dict[str, Any], show_full_events: bool = False) -> Group:
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
    footer = Panel(
        Text.from_markup(
            "[bold cyan]f[/bold cyan] toggle full events   "
            "[bold cyan]q[/bold cyan] quit watcher   "
            f"events: [{'bold green' if show_full_events else 'dim'}]"
            f"{'full' if show_full_events else 'compact'}"
            f"[/{'bold green' if show_full_events else 'dim'}]"
        ),
        border_style="dim",
    )
    blocks = [header, _tasks_table(run), _evals_table(run), _draft_panel(run)]
    waiting_panel = _waiting_user_panel(run)
    if waiting_panel is not None:
        blocks.append(waiting_panel)
    blocks.extend([_events_table(run, show_full_events), footer])
    return Group(*blocks)


def _tasks_table(run: dict[str, Any]) -> Table:
    table = Table(title="Pipeline", title_style="bold", box=box.SIMPLE_HEAVY)
    table.add_column("State", no_wrap=True, style="bold")
    table.add_column("Worker", style="cyan")
    table.add_column("Task", style="bold")
    table.add_column("Goal", style="white")
    for task in run.get("tasks", []):
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


def _draft_panel(run: dict[str, Any]) -> Panel:
    drafts = []
    for artifact in run.get("artifacts", []):
        payload = artifact.get("payload", {})
        drafts.extend(payload.get("edited_drafts", []))
        drafts.extend(payload.get("drafts", []))
    if not drafts:
        return Panel("[dim]No drafts yet.[/dim]", title="Draft Preview", border_style="dim")
    lines = []
    for draft in drafts[-3:]:
        lines.append(f"[bold]{draft.get('channel', 'unknown')}[/bold] · {draft.get('status', 'draft')}\n{draft.get('text', '')}")
    return Panel("\n\n".join(lines), title="Draft Preview", border_style="green")


def _waiting_user_panel(run: dict[str, Any]) -> Panel | None:
    if run.get("status") != "waiting_user":
        return None
    message = _latest_event_payload(run, "l2_message_user").get("message") or run.get("output", {}).get("requested_edit")
    if not message:
        return None
    body = Text.from_markup(
        "[bold magenta]L2 is asking for your input[/bold magenta]\n\n"
        f"{message}\n\n"
        "[dim]Type your answer in the prompt below. The watcher will resume this same run automatically.[/dim]"
    )
    return Panel(body, title="User Input Required", border_style="magenta")


def _events_table(run: dict[str, Any], show_full_events: bool = False) -> Table:
    table = Table(title="Recent Events", title_style="bold", box=box.ROUNDED, show_lines=show_full_events)
    table.add_column("Event", style="bold magenta", no_wrap=True)
    table.add_column("Payload", overflow="fold")
    for event in run.get("events", [])[-5:]:
        table.add_row(event["event_type"], Text(_format_payload(event.get("payload", {}), show_full_events), style="dim"))
    return table


def _format_payload(payload: Any, show_full: bool) -> str:
    if show_full:
        return json.dumps(payload, indent=2, ensure_ascii=False, sort_keys=True)
    compact = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ": "))
    if len(compact) <= COMPACT_PAYLOAD_LIMIT:
        return compact
    return f"{compact[: COMPACT_PAYLOAD_LIMIT - 3]}..."


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
