#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from p1_real_common import approve_run, assert_status, create_run, find_duplicate_events, get_summary, load_inputs, request_json, require_capabilities, require_health, wait_for_run


def load_env_file(path_value: str | None) -> None:
    if not path_value:
        return
    path = Path(path_value)
    if not path.exists():
        raise SystemExit(f'env file does not exist: {path}')
    for raw_line in path.read_text(encoding='utf-8').splitlines():
        line = raw_line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        os.environ[key.strip()] = value.strip().strip('"').strip("'")


def has_duplicate_skip_evidence(metrics: dict, duplicate_events: dict[str, int]) -> bool:
    return (
        sum(duplicate_events.values()) > 0
        or int(metrics.get('sheet_duplicate_skipped') or 0) > 0
        or int(metrics.get('outreach_master_duplicate_skipped') or 0) > 0
    )


def artifact_payloads(run: dict, artifact_type: str) -> list[dict]:
    payloads: list[dict] = []
    for artifact in run.get('artifacts', []):
        if isinstance(artifact, dict) and artifact.get('artifact_type') == artifact_type and isinstance(artifact.get('payload'), dict):
            payloads.append(artifact['payload'])
    return payloads


def latest_outreach_drafts(run: dict) -> list[dict]:
    for payload in reversed(artifact_payloads(run, 'p1_outreach_drafts')):
        drafts = payload.get('outreach_drafts')
        if isinstance(drafts, list) and drafts:
            return [draft for draft in drafts if isinstance(draft, dict)]
    return []


def duplicate_sync_check(run: dict) -> dict:
    from l2l3_protocol.workers.p1_operator_worker import sync_google_sheets, sync_outreach_master

    drafts = latest_outreach_drafts(run)
    if not drafts:
        raise SystemExit('idempotency proof failed: completed run has no outreach draft artifacts')
    inputs = run.get('input', {}).get('inputs', {})
    if not isinstance(inputs, dict):
        raise SystemExit('idempotency proof failed: run inputs are not an object')
    approval_package = {'outreach_drafts': drafts}
    common_inputs = {**inputs, 'approval_package': approval_package, 'outreach_drafts': drafts}
    sheet_result = sync_google_sheets({'inputs': {**common_inputs, 'allow_google_sheet_write': True}}, {})
    outreach_result = sync_outreach_master({'inputs': {**common_inputs, 'allow_outreach_master_write': True}}, {})
    sheet_skipped = int((sheet_result.get('sync_result') or {}).get('skipped_duplicate_count') or 0)
    outreach_skipped = int((outreach_result.get('sync_result') or {}).get('skipped_duplicate_count') or 0)
    expected = len(drafts)
    if sheet_skipped < expected or outreach_skipped < expected:
        raise SystemExit(
            'idempotency proof failed: duplicate sync did not skip every draft; '
            f'expected={expected}; sheet_skipped={sheet_skipped}; outreach_skipped={outreach_skipped}'
        )
    return {'expected_drafts': expected, 'sheet_duplicate_skipped': sheet_skipped, 'outreach_master_duplicate_skipped': outreach_skipped}


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a real P1 approval flow twice and verify duplicate writes are skipped.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--inputs-json')
    parser.add_argument('--run-id', help='Verify repeated approval idempotency on an existing completed real P1 run.')
    parser.add_argument('--env-file')
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args()

    load_env_file(args.env_file)
    require_health(args.base_url)
    require_capabilities(args.base_url)
    if args.run_id:
        run_id = args.run_id
        first = request_json(f'{args.base_url}/runs/{run_id}')
    else:
        if not args.inputs_json:
            raise SystemExit('idempotency proof requires --inputs-json or --run-id')
        inputs = load_inputs(args.inputs_json)
        created = create_run(args.base_url, 'Run P1 idempotency proof', inputs, require_human_approval=True)
        run_id = created['id']
        first = wait_for_run(args.base_url, run_id, args.timeout_seconds)
        assert_status(first, {'waiting_approval', 'completed'})
        if first['status'] == 'waiting_approval':
            approve_run(args.base_url, run_id)
            first = wait_for_run(args.base_url, run_id, args.timeout_seconds)
    assert_status(first, {'completed'})
    summary = get_summary(args.base_url, run_id)
    latest_metrics = summary.get('latest_metrics', {}) if isinstance(summary.get('latest_metrics'), dict) else {}
    duplicate_events = find_duplicate_events(first)
    duplicate_worker_check = duplicate_sync_check(first)
    duplicate_skip = has_duplicate_skip_evidence(latest_metrics, duplicate_events)
    print(json.dumps({'run_id': run_id, 'latest_metrics': latest_metrics, 'duplicate_events': duplicate_events, 'duplicate_worker_check': duplicate_worker_check, 'idempotency_mode': 'duplicate_worker_check' if not duplicate_skip else 'duplicate_skip'}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
