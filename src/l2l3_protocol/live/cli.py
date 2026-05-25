from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import select
import sys
import termios
import tty
from collections.abc import Iterator

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt

from l2l3_protocol.live.client import LiveApiClient
from l2l3_protocol.live.render import render_run_snapshot


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "waiting_approval", "waiting_user"}
DEFAULT_TREND_RADAR_GOAL = "Find AI/dev trends and produce reviewed build-in-public draft."


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch ABRT L2/L3 runs in a live terminal dashboard.")
    parser.add_argument("--api-url", default="http://localhost:8080")
    subparsers = parser.add_subparsers(dest="command", required=True)
    start = subparsers.add_parser("start", help="Start a real pipeline run from explicit input data.")
    start.add_argument("name", choices=["trend-radar"])
    start.add_argument("--query", required=True, help="Real search query for the trend collector.")
    start.add_argument(
        "--provider",
        dest="providers",
        action="append",
        choices=["github", "arxiv", "huggingface"],
        required=True,
        help="Real source provider to query. Repeat for multiple providers.",
    )
    start.add_argument("--channel", dest="channels", action="append", required=True, help="Target channel. Repeat for multiple channels.")
    start.add_argument("--max-results", type=int, default=5, help="Maximum real results per provider.")
    start.add_argument("--goal", default=DEFAULT_TREND_RADAR_GOAL)
    watch = subparsers.add_parser("watch")
    watch.add_argument("run_id")
    return parser.parse_args()


async def start_run(api_url: str, name: str, query: str, providers: list[str], channels: list[str], max_results: int, goal: str) -> None:
    if name != "trend-radar":
        raise ValueError(f"unknown pipeline: {name}")
    if max_results < 1:
        raise ValueError("max-results must be >= 1")
    client = LiveApiClient(api_url)
    await client.sync_registry()
    run = await client.create_trend_radar_run(goal=goal, query=query, providers=providers, channels=channels, max_results=max_results)
    await watch_run(api_url, run["id"], interactive=True)


async def watch_run(api_url: str, run_id: str, interactive: bool = False) -> None:
    client = LiveApiClient(api_url)
    console = Console()
    latest = await client.get_run(run_id)
    show_full_events = False
    while True:
        latest, user_quit, show_full_events = await _watch_until_terminal(client, console, run_id, latest, show_full_events)
        if user_quit or not interactive:
            break
        if latest["status"] == "waiting_user":
            message = Prompt.ask("[bold magenta]Reply to L2[/bold magenta]")
            latest = await client.send_message(run_id, message)
            continue
        if latest["status"] == "waiting_approval":
            choice = Prompt.ask("Approve draft?", choices=["approve", "reject", "edit", "quit"], default="approve")
            if choice == "approve":
                latest = await client.control(run_id, "approve", {})
                continue
            if choice == "reject":
                reason = Prompt.ask("Reason")
                latest = await client.control(run_id, "reject", {"reason": reason})
                continue
            if choice == "edit":
                message = Prompt.ask("Edit request")
                latest = await client.control(run_id, "request_edit", {"message": message})
                continue
            break
        break
    console.print(render_run_snapshot(latest, show_full_events, height=console.size.height))


async def _watch_until_terminal(
    client: LiveApiClient,
    console: Console,
    run_id: str,
    latest: dict,
    show_full_events: bool,
) -> tuple[dict, bool, bool]:
    user_quit = False
    controls_enabled = sys.stdin.isatty()
    with _terminal_key_mode(controls_enabled):
        with Live(
            render_run_snapshot(latest, show_full_events, height=console.size.height),
            console=console,
            refresh_per_second=6,
            screen=True,
            transient=False,
            redirect_stdout=False,
            redirect_stderr=False,
        ) as live:
            next_poll_at = asyncio.get_running_loop().time()
            while latest["status"] not in TERMINAL_STATUSES:
                key = _read_key_nonblocking() if controls_enabled else None
                if key == "f":
                    show_full_events = not show_full_events
                    live.update(render_run_snapshot(latest, show_full_events, height=console.size.height))
                elif key == "q":
                    user_quit = True
                    break

                now = asyncio.get_running_loop().time()
                if now >= next_poll_at:
                    latest = await client.get_run(run_id)
                    live.update(render_run_snapshot(latest, show_full_events, height=console.size.height))
                    next_poll_at = now + 1
                await asyncio.sleep(0.1)
            live.update(render_run_snapshot(latest, show_full_events, height=console.size.height))
    return latest, user_quit, show_full_events


@contextmanager
def _terminal_key_mode(enabled: bool) -> Iterator[None]:
    if not enabled:
        yield
        return
    fd = sys.stdin.fileno()
    previous = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        yield
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, previous)


def _read_key_nonblocking() -> str | None:
    ready, _, _ = select.select([sys.stdin], [], [], 0)
    if not ready:
        return None
    return sys.stdin.read(1)


def main() -> None:
    args = parse_args()
    if args.command == "start":
        asyncio.run(start_run(args.api_url, args.name, args.query, args.providers, args.channels, args.max_results, args.goal))
    elif args.command == "watch":
        asyncio.run(watch_run(args.api_url, args.run_id, interactive=True))
