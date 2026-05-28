from __future__ import annotations

import argparse
import json

from real_playbook_common import request_json, review_query_string
from l2l3_protocol.runtime.self_improvement import render_recent_system_review_markdown


def main() -> None:
    parser = argparse.ArgumentParser(description='Run real CLI/script review flows for recent runs and learned-system reports.')
    parser.add_argument('--api-url', default='http://localhost:8080')
    subparsers = parser.add_subparsers(dest='command', required=True)

    recent = subparsers.add_parser('recent')
    recent.add_argument('--limit', type=int, default=50)
    recent.add_argument('--playbook-key')
    recent.add_argument('--since-hours', type=int)
    recent.add_argument('--format', choices=['json', 'markdown'], default='markdown')

    learned = subparsers.add_parser('learned')
    learned.add_argument('--playbook-key')
    learned.add_argument('--since-hours', type=int)
    learned.add_argument('--format', choices=['json', 'markdown'], default='markdown')

    regressions = subparsers.add_parser('regressions')
    regressions.add_argument('--playbook-key')
    regressions.add_argument('--format', choices=['json'], default='json')

    args = parser.parse_args()
    api_url = args.api_url.rstrip('/')

    if args.command == 'recent':
        payload = {'limit': args.limit}
        if args.playbook_key is not None:
            payload['playbook_key'] = args.playbook_key
        if args.since_hours is not None:
            payload['since_hours'] = args.since_hours
        review = request_json(f'{api_url}/system-reviews/recent', method='POST', payload=payload)
        if args.format == 'json':
            print(json.dumps(review, indent=2, ensure_ascii=False))
        else:
            print(render_recent_system_review_markdown(review if isinstance(review, dict) else {}))
        return

    if args.command == 'learned':
        report = request_json(f'{api_url}/reports/system-learning{review_query_string(playbook_key=args.playbook_key, since_hours=args.since_hours)}')
        if args.format == 'json':
            print(json.dumps(report, indent=2, ensure_ascii=False))
        else:
            print((report if isinstance(report, dict) else {}).get('markdown') or json.dumps(report, indent=2, ensure_ascii=False))
        return

    if args.command == 'regressions':
        cases = request_json(f'{api_url}/regression-cases{review_query_string(playbook_key=args.playbook_key)}')
        print(json.dumps(cases, indent=2, ensure_ascii=False))
        return


if __name__ == '__main__':
    main()
