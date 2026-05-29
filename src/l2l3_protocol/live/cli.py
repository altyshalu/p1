from __future__ import annotations

import argparse
import asyncio
import json

from l2l3_protocol.live.client import LiveApiClient
from l2l3_protocol.live.tui import LiveRunApp
from l2l3_protocol.runtime.self_improvement import render_recent_system_review_markdown


DEFAULT_TREND_RADAR_GOAL = 'Find AI/dev trends and produce reviewed build-in-public draft.'


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description='Watch ABRT L2/L3 runs in a live terminal dashboard.')
    parser.add_argument('--api-url', default='http://localhost:8080')
    subparsers = parser.add_subparsers(dest='command', required=True)
    start = subparsers.add_parser('start', help='Start a real pipeline run from explicit input data.')
    start.add_argument('name', choices=['trend-radar', 'goal-discovery'])
    start.add_argument('--query', help='Real search query for the trend collector.')
    start.add_argument(
        '--provider',
        dest='providers',
        action='append',
        choices=['github', 'arxiv', 'huggingface'],
        help='Real source provider to query. Repeat for multiple providers.',
    )
    start.add_argument('--channel', dest='channels', action='append', help='Target channel. Repeat for multiple channels.')
    start.add_argument('--max-results', type=int, default=5, help='Maximum real results per provider.')
    start.add_argument('--context', dest='context', action='append', default=[], help='Optional context line for goal discovery. Repeat for multiple context items.')
    start.add_argument('--goal', help='Goal or intent to run.')
    watch = subparsers.add_parser('watch')
    watch.add_argument('run_id')
    review = subparsers.add_parser('review')
    review_subparsers = review.add_subparsers(dest='review_command', required=True)
    recent = review_subparsers.add_parser('recent')
    recent.add_argument('--limit', type=int, default=50)
    recent.add_argument('--playbook-key')
    recent.add_argument('--since-hours', type=int)
    recent.add_argument('--format', choices=['json', 'markdown'], default='markdown')
    report = subparsers.add_parser('report')
    report_subparsers = report.add_subparsers(dest='report_command', required=True)
    learned = report_subparsers.add_parser('learned')
    learned.add_argument('--playbook-key')
    learned.add_argument('--since-hours', type=int)
    learned.add_argument('--format', choices=['json', 'markdown'], default='markdown')
    regressions = report_subparsers.add_parser('regressions')
    regressions.add_argument('--playbook-key')
    regressions.add_argument('--format', choices=['json'], default='json')
    return parser.parse_args()


async def start_run(
    api_url: str,
    name: str,
    goal: str | None,
    query: str | None,
    providers: list[str] | None,
    channels: list[str] | None,
    max_results: int,
    context: list[str],
) -> None:
    client = LiveApiClient(api_url)
    await client.sync_registry()
    if name == 'trend-radar':
        if max_results < 1:
            raise ValueError('max-results must be >= 1')
        if not query:
            raise ValueError('trend-radar requires --query')
        if not providers:
            raise ValueError('trend-radar requires at least one --provider')
        if not channels:
            raise ValueError('trend-radar requires at least one --channel')
        run = await client.create_trend_radar_run(
            goal=goal or DEFAULT_TREND_RADAR_GOAL,
            query=query,
            providers=providers,
            channels=channels,
            max_results=max_results,
        )
        await watch_run(api_url, run['id'])
        return
    if name == 'goal-discovery':
        if not goal:
            raise ValueError('goal-discovery requires --goal')
        run = await client.create_goal_discovery_run(goal=goal, context=context)
        await watch_run(api_url, run['id'])
        return
    raise ValueError(f'unknown pipeline: {name}')


async def watch_run(api_url: str, run_id: str) -> None:
    await LiveRunApp(api_url=api_url, run_id=run_id).run_async()


async def review_recent_runs(api_url: str, limit: int, playbook_key: str | None, since_hours: int | None, output_format: str) -> None:
    if limit < 1:
        raise ValueError('limit must be >= 1')
    client = LiveApiClient(api_url)
    review = await client.create_recent_system_review(limit=limit, playbook_key=playbook_key, since_hours=since_hours)
    if output_format == 'json':
        print(json.dumps(review, indent=2, ensure_ascii=False))
        return
    print(render_recent_system_review_markdown(review))


async def report_learnings(api_url: str, playbook_key: str | None, since_hours: int | None, output_format: str) -> None:
    client = LiveApiClient(api_url)
    report = await client.get_system_learning_report(playbook_key=playbook_key, since_hours=since_hours)
    if output_format == 'json':
        print(json.dumps(report, indent=2, ensure_ascii=False))
        return
    print(report.get('markdown') or json.dumps(report, indent=2, ensure_ascii=False))


async def list_regressions(api_url: str, playbook_key: str | None) -> None:
    client = LiveApiClient(api_url)
    payload = await client.list_regression_cases(playbook_key=playbook_key)
    print(json.dumps(payload, indent=2, ensure_ascii=False))


def main() -> None:
    args = parse_args()
    if args.command == 'start':
        asyncio.run(start_run(args.api_url, args.name, args.goal, args.query, args.providers, args.channels, args.max_results, args.context))
    elif args.command == 'watch':
        asyncio.run(watch_run(args.api_url, args.run_id))
    elif args.command == 'review':
        asyncio.run(review_recent_runs(args.api_url, args.limit, args.playbook_key, args.since_hours, args.format))
    elif args.command == 'report' and args.report_command == 'learned':
        asyncio.run(report_learnings(args.api_url, args.playbook_key, args.since_hours, args.format))
    elif args.command == 'report' and args.report_command == 'regressions':
        asyncio.run(list_regressions(args.api_url, args.playbook_key))


if __name__ == '__main__':
    main()
