from __future__ import annotations

import argparse
import asyncio
import json

from l2l3_protocol.live.client import LiveApiClient
from l2l3_protocol.live.tui import LiveRunApp


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
    review = subparsers.add_parser("review")
    review_subparsers = review.add_subparsers(dest="review_command", required=True)
    recent = review_subparsers.add_parser("recent")
    recent.add_argument("--limit", type=int, default=50)
    recent.add_argument("--playbook-key", default="build-in-public-trend-radar")
    return parser.parse_args()


async def start_run(api_url: str, name: str, query: str, providers: list[str], channels: list[str], max_results: int, goal: str) -> None:
    if name != "trend-radar":
        raise ValueError(f"unknown pipeline: {name}")
    if max_results < 1:
        raise ValueError("max-results must be >= 1")
    client = LiveApiClient(api_url)
    await client.sync_registry()
    run = await client.create_trend_radar_run(goal=goal, query=query, providers=providers, channels=channels, max_results=max_results)
    await watch_run(api_url, run["id"])


async def watch_run(api_url: str, run_id: str) -> None:
    await LiveRunApp(api_url=api_url, run_id=run_id).run_async()


async def review_recent_runs(api_url: str, limit: int, playbook_key: str | None) -> None:
    if limit < 1:
        raise ValueError("limit must be >= 1")
    client = LiveApiClient(api_url)
    review = await client.create_recent_system_review(limit=limit, playbook_key=playbook_key)
    print(json.dumps(review, indent=2, ensure_ascii=False))


def main() -> None:
    args = parse_args()
    if args.command == "start":
        asyncio.run(start_run(args.api_url, args.name, args.query, args.providers, args.channels, args.max_results, args.goal))
    elif args.command == "watch":
        asyncio.run(watch_run(args.api_url, args.run_id))
    elif args.command == "review":
        asyncio.run(review_recent_runs(args.api_url, args.limit, args.playbook_key))
