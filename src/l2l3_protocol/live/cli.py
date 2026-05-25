from __future__ import annotations

import argparse
import asyncio

from rich.console import Console
from rich.live import Live
from rich.prompt import Prompt

from l2l3_protocol.live.client import LiveApiClient
from l2l3_protocol.live.render import render_run_snapshot


TERMINAL_STATUSES = {"completed", "failed", "cancelled", "waiting_approval", "waiting_user"}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Watch ABRT L2/L3 runs in a live terminal dashboard.")
    parser.add_argument("--api-url", default="http://localhost:8080")
    subparsers = parser.add_subparsers(dest="command", required=True)
    demo = subparsers.add_parser("demo")
    demo.add_argument("name", choices=["trend-radar"])
    watch = subparsers.add_parser("watch")
    watch.add_argument("run_id")
    return parser.parse_args()


async def run_demo(api_url: str, name: str) -> None:
    if name != "trend-radar":
        raise ValueError(f"unknown demo: {name}")
    client = LiveApiClient(api_url)
    await client.sync_registry()
    run = await client.create_trend_radar_demo()
    await watch_run(api_url, run["id"], interactive=True)


async def watch_run(api_url: str, run_id: str, interactive: bool = False) -> None:
    client = LiveApiClient(api_url)
    console = Console()
    latest = await client.get_run(run_id)
    with Live(render_run_snapshot(latest), console=console, refresh_per_second=4) as live:
        while latest["status"] not in TERMINAL_STATUSES:
            await asyncio.sleep(1)
            latest = await client.get_run(run_id)
            live.update(render_run_snapshot(latest))
        live.update(render_run_snapshot(latest))

    if interactive and latest["status"] == "waiting_approval":
        choice = Prompt.ask("Approve draft?", choices=["approve", "reject", "edit", "quit"], default="approve")
        if choice == "approve":
            latest = await client.control(run_id, "approve", {})
        elif choice == "reject":
            reason = Prompt.ask("Reason")
            latest = await client.control(run_id, "reject", {"reason": reason})
        elif choice == "edit":
            message = Prompt.ask("Edit request")
            latest = await client.control(run_id, "request_edit", {"message": message})
        console.print(render_run_snapshot(latest))


def main() -> None:
    args = parse_args()
    if args.command == "demo":
        asyncio.run(run_demo(args.api_url, args.name))
    elif args.command == "watch":
        asyncio.run(watch_run(args.api_url, args.run_id, interactive=True))
