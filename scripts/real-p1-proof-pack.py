#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

CONFIG_MARKERS = (
    'missing required environment variable',
    'missing required input',
    'missing_required_keys',
    'env file not found',
    'verify-sheet requires spreadsheet_id',
    'verify-sheet requested but preview did not include any lead_ids',
    'HTTP 401',
    'HTTP 403',
)
DEPENDENCY_MARKERS = (
    'HTTP 429',
    'timed out',
    'timeout',
    'temporary failure',
    'connection reset',
)


def classify_failure(output: str) -> str:
    lowered = output.lower()
    if any(marker.lower() in lowered for marker in CONFIG_MARKERS):
        return 'fail_external_config'
    if any(marker.lower() in lowered for marker in DEPENDENCY_MARKERS):
        return 'fail_external_dependency'
    return 'fail_internal'


def parse_json_output(output: str) -> dict[str, Any] | None:
    if not output.strip():
        return None
    try:
        payload = json.loads(output)
    except json.JSONDecodeError:
        return None
    return payload if isinstance(payload, dict) else None


def run_step(name: str, command: list[str]) -> dict[str, Any]:
    completed = subprocess.run(command, capture_output=True, text=True)
    stdout = completed.stdout.strip()
    stderr = completed.stderr.strip()
    combined = '\n'.join(part for part in (stdout, stderr) if part)
    status = 'pass' if completed.returncode == 0 else classify_failure(combined)
    parsed = parse_json_output(stdout)
    step: dict[str, Any] = {
        'name': name,
        'status': status,
        'returncode': completed.returncode,
        'command': command,
        'stdout': stdout,
        'stderr': stderr,
    }
    if parsed is not None:
        step['json'] = parsed
    return step


SKIPPED_STATUS = 'skipped'


def summarize_overall(steps: list[dict[str, Any]]) -> str:
    statuses = [str(step['status']) for step in steps if step['status'] != SKIPPED_STATUS]
    if not statuses:
        return SKIPPED_STATUS
    for candidate in ('fail_internal', 'fail_external_dependency', 'fail_external_config'):
        if candidate in statuses:
            return candidate
    return 'pass'


def build_skipped_step(name: str, reason: str) -> dict[str, Any]:
    return {'name': name, 'status': SKIPPED_STATUS, 'reason': reason}


def collect_action_items(steps: list[dict[str, Any]]) -> list[str]:
    items: list[str] = []
    for step in steps:
        if step.get('name') == 'readiness':
            payload = step.get('json') or {}
            missing = payload.get('missing_required_keys')
            if isinstance(missing, list) and missing:
                for key in missing:
                    items.append(f'Set required env key: {key}')
            path_checks = payload.get('path_checks')
            if isinstance(path_checks, dict):
                for key, ok in path_checks.items():
                    if not ok:
                        items.append(f'Create or mount required path for {key}')
        if step.get('status') == SKIPPED_STATUS:
            reason = str(step.get('reason') or '')
            if 'full_inputs_json' in reason:
                items.append('Provide --full-inputs-json for full proof execution')
            elif 'cache_inputs_json' in reason:
                items.append('Provide --cache-inputs-json for cache proof execution')
            elif 'idempotency_inputs_json' in reason:
                items.append('Provide --idempotency-inputs-json for idempotency proof execution')
        if step.get('status') == 'fail_external_dependency':
            items.append(f'Investigate external dependency instability in step {step.get("name")}')
        if step.get('status') == 'fail_internal':
            items.append(f'Fix backend/runtime failure in step {step.get("name")}')
    deduped: list[str] = []
    seen: set[str] = set()
    for item in items:
        if item not in seen:
            deduped.append(item)
            seen.add(item)
    return deduped


def main() -> int:
    parser = argparse.ArgumentParser(description='Run the real P1 proof matrix as one operator proof-pack.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--mode', choices=['full_pipeline', 'source_only', 'existing_dossiers'], default='full_pipeline')
    parser.add_argument('--full-inputs-json')
    parser.add_argument('--cache-inputs-json')
    parser.add_argument('--idempotency-inputs-json')
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    parser.add_argument('--skip-cache', action='store_true')
    parser.add_argument('--skip-idempotency', action='store_true')
    parser.add_argument('--skip-full', action='store_true')
    args = parser.parse_args()

    script_dir = Path(__file__).resolve().parent
    python_bin = sys.executable
    steps: list[dict[str, Any]] = []

    readiness_cmd = [
        python_bin,
        str(script_dir / 'real-p1-readiness.py'),
        '--base-url',
        args.base_url,
        '--env-file',
        args.env_file,
        '--mode',
        args.mode,
    ]
    if args.full_inputs_json:
        readiness_cmd.extend(['--inputs-json', args.full_inputs_json])
    steps.append(run_step('readiness', readiness_cmd))

    if not args.skip_full and args.full_inputs_json:
        full_cmd = [
            python_bin,
            str(script_dir / 'real-p1-full-proof.py'),
            '--base-url',
            args.base_url,
            '--inputs-json',
            args.full_inputs_json,
            '--timeout-seconds',
            str(args.timeout_seconds),
        ]
        steps.append(run_step('full_proof', full_cmd))
    elif not args.skip_full:
        steps.append(build_skipped_step('full_proof', 'full_inputs_json not provided'))

    if not args.skip_cache and args.cache_inputs_json:
        cache_cmd = [
            python_bin,
            str(script_dir / 'real-p1-cache-proof.py'),
            '--base-url',
            args.base_url,
            '--inputs-json',
            args.cache_inputs_json,
            '--timeout-seconds',
            str(args.timeout_seconds),
        ]
        steps.append(run_step('cache_proof', cache_cmd))
    elif not args.skip_cache:
        steps.append(build_skipped_step('cache_proof', 'cache_inputs_json not provided'))

    if not args.skip_idempotency and args.idempotency_inputs_json:
        idempotency_cmd = [
            python_bin,
            str(script_dir / 'real-p1-idempotency-proof.py'),
            '--base-url',
            args.base_url,
            '--inputs-json',
            args.idempotency_inputs_json,
            '--timeout-seconds',
            str(args.timeout_seconds),
        ]
        steps.append(run_step('idempotency_proof', idempotency_cmd))
    elif not args.skip_idempotency:
        steps.append(build_skipped_step('idempotency_proof', 'idempotency_inputs_json not provided'))

    overall = summarize_overall(steps)
    report = {
        'overall_status': overall,
        'base_url': args.base_url,
        'env_file': args.env_file,
        'mode': args.mode,
        'action_items': collect_action_items(steps),
        'steps': steps,
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if overall == 'pass' else 1


if __name__ == '__main__':
    raise SystemExit(main())
