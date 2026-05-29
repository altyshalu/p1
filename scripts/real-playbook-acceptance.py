from __future__ import annotations

import argparse
import json

from real_playbook_common import (
    SUCCESSFUL_TERMINAL,
    assess_playbook_readiness,
    create_run_payload,
    fetch_registry_bundle,
    load_inputs,
    request_json,
    validate_terminal_run,
    wait_for_terminal_run,
)


def main() -> None:
    parser = argparse.ArgumentParser(description='Run a real acceptance check for any seeded playbook.')
    parser.add_argument('--api-url', default='http://localhost:8080')
    parser.add_argument('--playbook-key', required=True)
    parser.add_argument('--goal', required=True)
    parser.add_argument('--inputs-json')
    parser.add_argument('--inputs-file')
    parser.add_argument('--timeout-seconds', type=int, default=900)
    parser.add_argument('--require-human-approval', action=argparse.BooleanOptionalAction, default=True)
    parser.add_argument('--expected-status', dest='expected_statuses', action='append')
    args = parser.parse_args()

    api_url = args.api_url.rstrip('/')
    health = request_json(f'{api_url}/health')
    if not isinstance(health, dict) or health.get('status') != 'ok':
        raise RuntimeError(f'real API health check failed: {health}')

    sync = request_json(f'{api_url}/hub/sync/yaml', method='POST')
    if not isinstance(sync, dict) or int(sync.get('synced', 0)) <= 0:
        raise RuntimeError(f'real Hub sync failed: {sync}')

    inputs = load_inputs(inputs_json=args.inputs_json, inputs_file=args.inputs_file)
    readiness = assess_playbook_readiness(fetch_registry_bundle(api_url, args.playbook_key), inputs=inputs)
    if not readiness['summary']['ready']:
        raise RuntimeError(f'playbook is not ready for a real run: {readiness["issues"]}')

    created = request_json(
        f'{api_url}/runs',
        method='POST',
        payload=create_run_payload(
            playbook_key=args.playbook_key,
            goal=args.goal,
            inputs=inputs,
            require_human_approval=args.require_human_approval,
        ),
    )
    if not isinstance(created, dict) or not created.get('id'):
        raise RuntimeError(f'real run creation failed: {created}')

    latest = wait_for_terminal_run(api_url, str(created['id']), args.timeout_seconds)
    summary = validate_terminal_run(latest, expected_statuses=set(args.expected_statuses or SUCCESSFUL_TERMINAL))
    print(json.dumps(summary, indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
