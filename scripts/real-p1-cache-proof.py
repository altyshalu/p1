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

from p1_real_common import assert_status, create_run, get_summary, load_inputs, require_capabilities, require_health, wait_for_run


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


def main() -> int:
    parser = argparse.ArgumentParser(description='Run two real comparable P1 source-only runs and verify cache/source-batch reuse signals.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--inputs-json', required=True)
    parser.add_argument('--env-file')
    parser.add_argument('--timeout-seconds', type=int, default=1200)
    args = parser.parse_args()

    load_env_file(args.env_file)
    inputs = load_inputs(args.inputs_json)
    require_health(args.base_url)
    require_capabilities(args.base_url)
    first = create_run(args.base_url, 'Run P1 source-only cache proof (first run)', inputs, require_human_approval=False)
    first_run = wait_for_run(args.base_url, first['id'], args.timeout_seconds)
    assert_status(first_run, {'completed', 'waiting_approval'})
    second = create_run(args.base_url, 'Run P1 source-only cache proof (second run)', inputs, require_human_approval=False)
    second_run = wait_for_run(args.base_url, second['id'], args.timeout_seconds)
    assert_status(second_run, {'completed', 'waiting_approval'})
    second_summary = get_summary(args.base_url, second['id'])
    latest_metrics = second_summary.get('latest_metrics', {}) if isinstance(second_summary.get('latest_metrics'), dict) else {}
    cache_hits = int(latest_metrics.get('provider_cache_hits') or 0)
    if cache_hits <= 0:
        raise SystemExit(f'cache proof failed: second comparable run reported no provider_cache_hits; metrics={latest_metrics}')
    print(json.dumps({'first_run_id': first['id'], 'second_run_id': second['id'], 'second_metrics': latest_metrics}, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
