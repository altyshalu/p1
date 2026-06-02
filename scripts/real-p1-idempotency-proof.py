#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from p1_real_common import approve_run, assert_status, create_run, find_duplicate_events, get_summary, load_inputs, require_capabilities, require_health, wait_for_run


SYNC_METRIC_KEYS = ('sheet_written', 'outreach_master_written', 'data_lake_written')


def sync_metrics_stable(before: dict, after: dict) -> bool:
    after_counts = [int(after.get(key) or 0) for key in SYNC_METRIC_KEYS]
    return sum(after_counts) > 0 and all(int(before.get(key) or 0) == int(after.get(key) or 0) for key in SYNC_METRIC_KEYS)


def has_duplicate_skip_evidence(metrics: dict, duplicate_events: dict[str, int]) -> bool:
    return (
        sum(duplicate_events.values()) > 0
        or int(metrics.get('sheet_duplicate_skipped') or 0) > 0
        or int(metrics.get('outreach_master_duplicate_skipped') or 0) > 0
    )


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a real P1 approval flow twice and verify duplicate writes are skipped.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--inputs-json', required=True)
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    args = parser.parse_args()

    inputs = load_inputs(args.inputs_json)
    require_health(args.base_url)
    require_capabilities(args.base_url)
    created = create_run(args.base_url, 'Run P1 idempotency proof', inputs, require_human_approval=True)
    first = wait_for_run(args.base_url, created['id'], args.timeout_seconds)
    assert_status(first, {'waiting_approval', 'completed'})
    if first['status'] == 'waiting_approval':
        approve_run(args.base_url, created['id'])
        first = wait_for_run(args.base_url, created['id'], args.timeout_seconds)
    assert_status(first, {'completed'})
    first_summary = get_summary(args.base_url, created['id'])
    first_metrics = first_summary.get('latest_metrics', {}) if isinstance(first_summary.get('latest_metrics'), dict) else {}

    approve_run(args.base_url, created['id'])
    second = wait_for_run(args.base_url, created['id'], args.timeout_seconds)
    assert_status(second, {'completed'})
    summary = get_summary(args.base_url, created['id'])
    latest_metrics = summary.get('latest_metrics', {}) if isinstance(summary.get('latest_metrics'), dict) else {}
    duplicate_events = find_duplicate_events(second)
    duplicate_skip = has_duplicate_skip_evidence(latest_metrics, duplicate_events)
    stable_noop = sync_metrics_stable(first_metrics, latest_metrics)
    if not duplicate_skip and not stable_noop:
        raise SystemExit(f'idempotency proof failed: no duplicate-skip or stable no-op evidence found; before={first_metrics}; after={latest_metrics}; events={duplicate_events}')
    print(json.dumps({'run_id': created['id'], 'latest_metrics': latest_metrics, 'duplicate_events': duplicate_events, 'idempotency_mode': 'duplicate_skip' if duplicate_skip else 'stable_noop'}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
