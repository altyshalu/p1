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
    'missing_runtime_inputs',
    'env file not found',
    'verify-sheet requires spreadsheet_id',
    'verify-sheet requested but preview did not include any lead_ids',
    'verify-outreach-master requires outreach_master_path',
    'verify-data-lake requires data_lake_dossier_path or dossier_output_path',
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
SKIPPED_STATUS = 'skipped'


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


def load_inputs_payload(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise SystemExit(f'inputs-json must contain a JSON object: {path}')
    return payload


def scenario_mode(path: str, fallback_mode: str) -> str:
    payload = load_inputs_payload(path)
    mode = payload.get('mode')
    if isinstance(mode, str) and mode.strip():
        return mode.strip()
    return fallback_mode


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
        step_name = str(step.get('name') or '')
        if step_name == 'readiness' or step_name.endswith('_preflight'):
            payload = step.get('json') or {}
            missing_keys = payload.get('missing_required_keys')
            if isinstance(missing_keys, list) and missing_keys:
                for key in missing_keys:
                    items.append(f'Set required env key: {key}')
            missing_inputs = payload.get('missing_runtime_inputs')
            if isinstance(missing_inputs, list) and missing_inputs:
                for key in missing_inputs:
                    items.append(f'Provide required runtime input: {key}')
            path_checks = payload.get('path_checks')
            if isinstance(path_checks, dict):
                for key, ok in path_checks.items():
                    if not ok:
                        items.append(f'Create, mount, or fix required path: {key}')
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


def scenario_preflight_step(
    python_bin: str,
    script_dir: Path,
    *,
    base_url: str,
    env_file: str,
    fallback_mode: str,
    scenario_name: str,
    inputs_json: str | None,
) -> dict[str, Any]:
    step_name = f'{scenario_name}_preflight'
    if not inputs_json:
        return build_skipped_step(step_name, f'{scenario_name}_inputs_json not provided')
    mode = scenario_mode(inputs_json, fallback_mode)
    command = [
        python_bin,
        str(script_dir / 'real-p1-readiness.py'),
        '--base-url',
        base_url,
        '--env-file',
        env_file,
        '--mode',
        mode,
        '--inputs-json',
        inputs_json,
    ]
    return run_step(step_name, command)


def should_skip_proof(preflight_step: dict[str, Any], *, force: bool) -> str | None:
    if force:
        return None
    if preflight_step.get('status') == SKIPPED_STATUS:
        return str(preflight_step.get('reason') or 'scenario preflight skipped')
    if preflight_step.get('status') != 'pass':
        return 'scenario preflight failed'
    return None


def append_full_verify_flags(command: list[str], args: argparse.Namespace) -> None:
    if args.verify_sheet:
        command.append('--verify-sheet')
    if args.verify_outreach_master:
        command.append('--verify-outreach-master')
    if args.verify_data_lake:
        command.append('--verify-data-lake')
    if args.verify_quality:
        command.append('--verify-quality')
    if args.google_service_account_path:
        command.extend(['--google-service-account-path', args.google_service_account_path])
    if args.approve:
        command.append('--approve')


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
    parser.add_argument('--force-after-readiness-failure', action='store_true')
    parser.add_argument('--approve', action='store_true')
    parser.add_argument('--verify-sheet', action='store_true')
    parser.add_argument('--verify-outreach-master', action='store_true')
    parser.add_argument('--verify-data-lake', action='store_true')
    parser.add_argument('--verify-quality', action='store_true')
    parser.add_argument('--google-service-account-path')
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
    readiness_step = run_step('readiness', readiness_cmd)
    steps.append(readiness_step)

    full_preflight = scenario_preflight_step(
        python_bin,
        script_dir,
        base_url=args.base_url,
        env_file=args.env_file,
        fallback_mode=args.mode,
        scenario_name='full',
        inputs_json=args.full_inputs_json,
    ) if not args.skip_full else build_skipped_step('full_preflight', 'full proof disabled')
    cache_preflight = scenario_preflight_step(
        python_bin,
        script_dir,
        base_url=args.base_url,
        env_file=args.env_file,
        fallback_mode=args.mode,
        scenario_name='cache',
        inputs_json=args.cache_inputs_json,
    ) if not args.skip_cache else build_skipped_step('cache_preflight', 'cache proof disabled')
    idempotency_preflight = scenario_preflight_step(
        python_bin,
        script_dir,
        base_url=args.base_url,
        env_file=args.env_file,
        fallback_mode=args.mode,
        scenario_name='idempotency',
        inputs_json=args.idempotency_inputs_json,
    ) if not args.skip_idempotency else build_skipped_step('idempotency_preflight', 'idempotency proof disabled')

    steps.extend([full_preflight, cache_preflight, idempotency_preflight])

    no_scenario_inputs = all(step.get('status') == SKIPPED_STATUS for step in (full_preflight, cache_preflight, idempotency_preflight))
    if readiness_step['status'] != 'pass' and no_scenario_inputs and not args.force_after_readiness_failure:
        if not args.skip_full:
            steps.append(build_skipped_step('full_proof', 'readiness failed'))
        if not args.skip_cache:
            steps.append(build_skipped_step('cache_proof', 'readiness failed'))
        if not args.skip_idempotency:
            steps.append(build_skipped_step('idempotency_proof', 'readiness failed'))
    else:
        if not args.skip_full:
            full_skip = should_skip_proof(full_preflight, force=args.force_after_readiness_failure)
            if full_skip is None and args.full_inputs_json:
                full_cmd = [
                    python_bin,
                    str(script_dir / 'real-p1-full-proof.py'),
                    '--base-url',
                    args.base_url,
                    '--inputs-json',
                    args.full_inputs_json,
                    '--env-file',
                    args.env_file,
                    '--timeout-seconds',
                    str(args.timeout_seconds),
                ]
                append_full_verify_flags(full_cmd, args)
                steps.append(run_step('full_proof', full_cmd))
            else:
                steps.append(build_skipped_step('full_proof', full_skip or 'full_inputs_json not provided'))

        if not args.skip_cache:
            cache_skip = should_skip_proof(cache_preflight, force=args.force_after_readiness_failure)
            if cache_skip is None and args.cache_inputs_json:
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
            else:
                steps.append(build_skipped_step('cache_proof', cache_skip or 'cache_inputs_json not provided'))

        if not args.skip_idempotency:
            idempotency_skip = should_skip_proof(idempotency_preflight, force=args.force_after_readiness_failure)
            if idempotency_skip is None and args.idempotency_inputs_json:
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
            else:
                steps.append(build_skipped_step('idempotency_proof', idempotency_skip or 'idempotency_inputs_json not provided'))

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
