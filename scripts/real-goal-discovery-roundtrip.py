from __future__ import annotations

import argparse
import json
from typing import Any

from real_playbook_common import (
    SUCCESSFUL_TERMINAL,
    assess_playbook_readiness,
    create_run_payload,
    fetch_registry_bundle,
    request_json,
    validate_terminal_run,
    wait_for_terminal_run,
)


def _goal_brief_artifact(run: dict[str, Any]) -> dict[str, Any] | None:
    artifacts = run.get('artifacts', [])
    if not isinstance(artifacts, list):
        return None
    for artifact in reversed(artifacts):
        if not isinstance(artifact, dict) or artifact.get('artifact_type') != 'goal_brief':
            continue
        payload = artifact.get('payload')
        if not isinstance(payload, dict):
            continue
        brief = payload.get('goal_brief')
        if isinstance(brief, dict):
            return brief
        return payload
    return None


def main() -> None:
    parser = argparse.ArgumentParser(description='Run a real unclear-goal roundtrip: discovery prompt, user reply, and final goal brief.')
    parser.add_argument('--api-url', default='http://localhost:8080')
    parser.add_argument('--goal', required=True)
    parser.add_argument('--context', action='append', default=[])
    parser.add_argument('--reply', required=True, help='Real user reply that clarifies the intent after the first waiting_user turn.')
    parser.add_argument('--timeout-seconds', type=int, default=900)
    args = parser.parse_args()

    api_url = args.api_url.rstrip('/')
    health = request_json(f'{api_url}/health')
    if not isinstance(health, dict) or health.get('status') != 'ok':
        raise RuntimeError(f'real API health check failed: {health}')

    sync = request_json(f'{api_url}/hub/sync/yaml', method='POST')
    if not isinstance(sync, dict) or int(sync.get('synced', 0)) <= 0:
        raise RuntimeError(f'real Hub sync failed: {sync}')

    inputs = {'context': args.context}
    readiness = assess_playbook_readiness(fetch_registry_bundle(api_url, 'goal-discovery'), inputs=inputs)
    if not readiness['summary']['ready']:
        raise RuntimeError(f'goal-discovery playbook is not ready: {readiness["issues"]}')

    created = request_json(
        f'{api_url}/runs',
        method='POST',
        payload=create_run_payload(
            playbook_key='goal-discovery',
            goal=args.goal,
            inputs=inputs,
            require_human_approval=False,
        ),
    )
    if not isinstance(created, dict) or not created.get('id'):
        raise RuntimeError(f'goal-discovery run creation failed: {created}')

    first = wait_for_terminal_run(api_url, str(created['id']), args.timeout_seconds)
    first_summary = validate_terminal_run(first, expected_statuses=SUCCESSFUL_TERMINAL)
    if first_summary['status'] != 'waiting_user':
        raise RuntimeError(f'goal-discovery first stage must pause for user clarification: {first_summary}')

    resumed = request_json(f"{api_url}/runs/{created['id']}/messages", method='POST', payload={'message': args.reply})
    if not isinstance(resumed, dict):
        raise RuntimeError(f'goal-discovery resume failed: {resumed}')

    final = wait_for_terminal_run(api_url, str(created['id']), args.timeout_seconds)
    final_summary = validate_terminal_run(final, expected_statuses={'completed'})
    goal_brief = _goal_brief_artifact(final)
    if not isinstance(goal_brief, dict):
        raise RuntimeError('goal-discovery final run is missing goal_brief artifact')
    if goal_brief.get('ready_for_execution') is not True:
        raise RuntimeError(f'goal_brief must mark ready_for_execution=true: {goal_brief}')

    print(
        json.dumps(
            {
                'run_id': created['id'],
                'first_stage': first_summary,
                'final_stage': final_summary,
                'goal_brief': goal_brief,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == '__main__':
    main()
