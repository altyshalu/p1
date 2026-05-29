#!/usr/bin/env python3
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


TERMINAL_RUN_STATUSES = {'completed', 'failed', 'waiting_approval', 'waiting_user'}


def request_json(url: str, method: str = 'GET', body: dict | None = None, timeout: int = 120) -> dict[str, Any]:
    data = None if body is None else json.dumps(body).encode('utf-8')
    headers = {'accept': 'application/json'}
    if body is not None:
        headers['content-type'] = 'application/json'
    try:
        with urlopen(Request(url, method=method, data=data, headers=headers), timeout=timeout) as response:
            payload = response.read().decode('utf-8')
    except HTTPError as exc:
        detail = exc.read().decode('utf-8', errors='replace') if exc.fp else ''
        raise SystemExit(f'{method} {url} failed: HTTP {exc.code} {detail}'.strip()) from exc
    except URLError as exc:
        raise SystemExit(f'{method} {url} failed: {exc.reason}') from exc
    return json.loads(payload)


def require_health(base_url: str) -> dict[str, Any]:
    health = request_json(f'{base_url}/health')
    if health.get('status') != 'ok':
        raise SystemExit(f'health check failed: {health}')
    return health


def require_capabilities(base_url: str) -> dict[str, Any]:
    capabilities = request_json(f'{base_url}/runtime/capabilities')
    if 'hermes' not in capabilities:
        raise SystemExit(f'runtime capabilities payload is missing hermes section: {capabilities}')
    return capabilities


def wait_for_run(base_url: str, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.time() + timeout_seconds
    last_status = 'unknown'
    while time.time() < deadline:
        run = request_json(f'{base_url}/runs/{run_id}')
        last_status = str(run.get('status'))
        if last_status in TERMINAL_RUN_STATUSES:
            return run
        time.sleep(2)
    raise SystemExit(f'run {run_id} did not reach a terminal state within {timeout_seconds}s; last_status={last_status}')


def create_run(base_url: str, goal: str, inputs: dict[str, Any], require_human_approval: bool | None = None) -> dict[str, Any]:
    payload = {
        'playbook_key': 'p1-operator-outreach',
        'goal': goal,
        'require_human_approval': bool(inputs.get('require_human_approval', True) if require_human_approval is None else require_human_approval),
        'inputs': inputs,
    }
    return request_json(f'{base_url}/runs', method='POST', body=payload)


def get_summary(base_url: str, run_id: str) -> dict[str, Any]:
    return request_json(f'{base_url}/runs/{run_id}/summary')


def approve_run(base_url: str, run_id: str) -> dict[str, Any]:
    return request_json(f'{base_url}/runs/{run_id}/control', method='POST', body={'action': 'approve', 'payload': {}})


def load_inputs(path: str) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding='utf-8'))
    if not isinstance(payload, dict):
        raise SystemExit('inputs-json must contain a JSON object')
    return payload


def assert_status(run: dict[str, Any], allowed: set[str]) -> None:
    status = str(run.get('status'))
    if status not in allowed:
        raise SystemExit(f'unexpected run status={status}; allowed={sorted(allowed)}; diagnosis={run.get("diagnosis")}')


def assert_summary_shape(summary: dict[str, Any]) -> None:
    required = {'status', 'playbook_key', 'goal', 'latest_metrics', 'artifact_counts', 'task_status_counts', 'pending_actions'}
    missing = sorted(required - set(summary))
    if missing:
        raise SystemExit(f'run summary is missing required fields: {missing}')


def find_duplicate_events(run: dict[str, Any]) -> dict[str, int]:
    counts = {
        'p1_external_sync_duplicate_skipped': 0,
        'p1_outreach_master_duplicate_skipped': 0,
        'p1_data_lake_duplicate_skipped': 0,
    }
    for event in run.get('events', []):
        event_type = event.get('event_type')
        if event_type in counts:
            counts[event_type] += int(event.get('payload', {}).get('skipped_duplicate_count') or 0)
    return counts
