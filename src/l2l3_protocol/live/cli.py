from __future__ import annotations

import argparse
import asyncio
from contextlib import contextmanager
import json
from pathlib import Path
import select
import sys
import termios
import tty
from collections.abc import Iterator

import yaml
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
    start.add_argument("--sources-file", required=True, type=Path, help="JSON/YAML file with real trend source results.")
    start.add_argument("--channel", dest="channels", action="append", required=True, help="Target channel. Repeat for multiple channels.")
    start.add_argument("--goal", default=DEFAULT_TREND_RADAR_GOAL)
    watch = subparsers.add_parser("watch")
    watch.add_argument("run_id")
    return parser.parse_args()


async def start_run(api_url: str, name: str, sources_file: Path, channels: list[str], goal: str) -> None:
    if name != "trend-radar":
        raise ValueError(f"unknown pipeline: {name}")
    sources = load_sources_file(sources_file)
    client = LiveApiClient(api_url)
    await client.sync_registry()
    run = await client.create_trend_radar_run(goal=goal, sources=sources, channels=channels)
    await watch_run(api_url, run["id"], interactive=True)


def load_sources_file(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        raise FileNotFoundError(f"sources file does not exist: {path}")
    raw_text = path.read_text()
    if path.suffix.lower() == ".json":
        payload = json.loads(raw_text)
    elif path.suffix.lower() in {".yaml", ".yml"}:
        payload = yaml.safe_load(raw_text)
    else:
        raise ValueError("sources file must be .json, .yaml, or .yml")

    sources = payload.get("sources") if isinstance(payload, dict) else payload
    if not isinstance(sources, list) or not sources:
        raise ValueError("sources file must contain a non-empty sources list")
    for index, group in enumerate(sources):
        if not isinstance(group, dict):
            raise ValueError(f"sources[{index}] must be an object")
        if not isinstance(group.get("source"), str) or not group["source"]:
            raise ValueError(f"sources[{index}].source must be a non-empty string")
        items = group.get("items")
        if not isinstance(items, list) or not items:
            raise ValueError(f"sources[{index}].items must be a non-empty list")
        for item_index, item in enumerate(items):
            if not isinstance(item, dict):
                raise ValueError(f"sources[{index}].items[{item_index}] must be an object")
            if not isinstance(item.get("title"), str) or not item["title"]:
                raise ValueError(f"sources[{index}].items[{item_index}].title must be a non-empty string")
            if not isinstance(item.get("url"), str) or not item["url"]:
                raise ValueError(f"sources[{index}].items[{item_index}].url must be a non-empty string")
    return sources


async def watch_run(api_url: str, run_id: str, interactive: bool = False) -> None:
    client = LiveApiClient(api_url)
    console = Console()
    latest = await client.get_run(run_id)
    show_full_events = False
    user_quit = False
    controls_enabled = sys.stdin.isatty()
    with _terminal_key_mode(controls_enabled):
        with Live(render_run_snapshot(latest, show_full_events), console=console, refresh_per_second=6) as live:
            next_poll_at = asyncio.get_running_loop().time()
            while latest["status"] not in TERMINAL_STATUSES:
                key = _read_key_nonblocking() if controls_enabled else None
                if key == "f":
                    show_full_events = not show_full_events
                    live.update(render_run_snapshot(latest, show_full_events))
                elif key == "q":
                    user_quit = True
                    break

                now = asyncio.get_running_loop().time()
                if now >= next_poll_at:
                    latest = await client.get_run(run_id)
                    live.update(render_run_snapshot(latest, show_full_events))
                    next_poll_at = now + 1
                await asyncio.sleep(0.1)
            live.update(render_run_snapshot(latest, show_full_events))

    if interactive and not user_quit and latest["status"] == "waiting_approval":
        choice = Prompt.ask("Approve draft?", choices=["approve", "reject", "edit", "quit"], default="approve")
        if choice == "approve":
            latest = await client.control(run_id, "approve", {})
        elif choice == "reject":
            reason = Prompt.ask("Reason")
            latest = await client.control(run_id, "reject", {"reason": reason})
        elif choice == "edit":
            message = Prompt.ask("Edit request")
            latest = await client.control(run_id, "request_edit", {"message": message})
        console.print(render_run_snapshot(latest, show_full_events))


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
        asyncio.run(start_run(args.api_url, args.name, args.sources_file, args.channels, args.goal))
    elif args.command == "watch":
        asyncio.run(watch_run(args.api_url, args.run_id, interactive=True))
