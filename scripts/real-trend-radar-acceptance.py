from __future__ import annotations

import argparse
import json

from real_playbook_common import (
    SUCCESSFUL_TERMINAL,
    create_run_payload,
    request_json,
    validate_terminal_run,
    wait_for_terminal_run,
)


def main() -> None:
    parser = argparse.ArgumentParser(description='Run a real build-in-public trend-radar acceptance check.')
    parser.add_argument('--api-url', default='http://localhost:8080')
    parser.add_argument('--query', default='AI agent evals runtime observability memory')
    parser.add_argument('--channel', default='x')
    parser.add_argument('--max-results', type=int, default=3)
    parser.add_argument('--timeout-seconds', type=int, default=900)
    args = parser.parse_args()

    api_url = args.api_url.rstrip('/')
    health = request_json(f'{api_url}/health')
    if not isinstance(health, dict) or health.get('status') != 'ok':
        raise RuntimeError(f'real API health check failed: {health}')

    sync = request_json(f'{api_url}/hub/sync/yaml', method='POST')
    if not isinstance(sync, dict) or int(sync.get('synced', 0)) <= 0:
        raise RuntimeError(f'real Hub sync failed: {sync}')

    run = request_json(
        f'{api_url}/runs',
        method='POST',
        payload=create_run_payload(
            playbook_key='build-in-public-trend-radar',
            goal='Real acceptance run for run diagnosis and improvement proposals.',
            inputs={
                'query': args.query,
                'providers': ['github', 'arxiv', 'huggingface'],
                'channels': [args.channel],
                'max_results': args.max_results,
            },
            require_human_approval=True,
        ),
    )
    if not isinstance(run, dict) or not run.get('id'):
        raise RuntimeError(f'real run creation failed: {run}')

    latest = wait_for_terminal_run(api_url, str(run['id']), args.timeout_seconds)
    print(json.dumps(validate_terminal_run(latest, expected_statuses=SUCCESSFUL_TERMINAL), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
