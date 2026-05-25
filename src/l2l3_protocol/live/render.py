from __future__ import annotations

from typing import Any

from rich.console import Group
from rich.panel import Panel
from rich.table import Table
from rich.text import Text


def render_run_snapshot(run: dict[str, Any]) -> Group:
    header = Panel(
        Text.from_markup(
            f"[bold]ABRT Live Run[/bold]\n"
            f"Process: [cyan]{run['process_key']}[/cyan]\n"
            f"Run: [dim]{run['id']}[/dim]\n"
            f"Status: [{_status_style(run['status'])}]{run['status']}[/{_status_style(run['status'])}]\n"
            f"Goal: {run['goal']}"
        ),
        title="L2/L3 Runtime",
    )
    return Group(header, _tasks_table(run), _evals_table(run), _draft_panel(run), _events_table(run))


def _tasks_table(run: dict[str, Any]) -> Table:
    table = Table(title="Pipeline")
    table.add_column("State", no_wrap=True)
    table.add_column("Worker")
    table.add_column("Task")
    table.add_column("Goal")
    for task in run.get("tasks", []):
        table.add_row(_state_icon(task["status"]), task["worker_profile"], task["task_type"], task.get("goal", ""))
    return table


def _evals_table(run: dict[str, Any]) -> Table:
    table = Table(title="Evals")
    table.add_column("Eval")
    table.add_column("Passed")
    table.add_column("Score")
    table.add_column("Threshold")
    for item in run.get("evals", []):
        table.add_row(
            item.get("eval_key") or "unknown",
            "yes" if item["passed"] else "no",
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
        return Panel("No drafts yet.", title="Draft Preview")
    lines = []
    for draft in drafts[-3:]:
        lines.append(f"[bold]{draft.get('channel', 'unknown')}[/bold] · {draft.get('status', 'draft')}\n{draft.get('text', '')}")
    return Panel("\n\n".join(lines), title="Draft Preview")


def _events_table(run: dict[str, Any]) -> Table:
    table = Table(title="Recent Events")
    table.add_column("Event")
    table.add_column("Payload")
    for event in run.get("events", [])[-5:]:
        table.add_row(event["event_type"], str(event.get("payload", {}))[:120])
    return table


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
