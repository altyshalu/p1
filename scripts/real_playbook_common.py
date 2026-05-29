from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

TERMINAL_OR_BLOCKED = {'completed', 'failed', 'cancelled', 'waiting_approval', 'waiting_user'}
SUCCESSFUL_TERMINAL = {'completed', 'waiting_approval', 'waiting_user'}


def request_json(url: str, *, method: str = 'GET', payload: dict[str, Any] | None = None, timeout: int = 60) -> dict[str, Any] | list[Any]:
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    request = Request(url, data=data, headers={'content-type': 'application/json'} if payload is not None else {}, method=method)
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.loads(response.read().decode('utf-8'))
    except HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        raise RuntimeError(f'real API request failed: {method} {url} -> {exc.code}: {body}') from exc


def load_inputs(*, inputs_json: str | None = None, inputs_file: str | None = None) -> dict[str, Any]:
    if inputs_json and inputs_file:
        raise RuntimeError('provide either --inputs-json or --inputs-file, not both')
    if inputs_json:
        payload = json.loads(inputs_json)
    elif inputs_file:
        payload = json.loads(Path(inputs_file).read_text())
    else:
        payload = {}
    if not isinstance(payload, dict):
        raise RuntimeError('playbook inputs must decode to a JSON object')
    return payload


def fetch_registry_bundle(api_url: str, playbook_key: str) -> dict[str, Any]:
    api_url = api_url.rstrip('/')
    playbook = request_json(f'{api_url}/hub/playbook/{playbook_key}')
    workers = request_json(f'{api_url}/hub/worker')
    tools = request_json(f'{api_url}/hub/tool')
    evals = request_json(f'{api_url}/hub/eval')
    capabilities = request_json(f'{api_url}/runtime/capabilities')
    return {
        'playbook': playbook,
        'workers': workers if isinstance(workers, list) else [],
        'tools': tools if isinstance(tools, list) else [],
        'evals': evals if isinstance(evals, list) else [],
        'capabilities': capabilities if isinstance(capabilities, dict) else {},
    }


def assess_playbook_readiness(bundle: dict[str, Any], *, inputs: dict[str, Any]) -> dict[str, Any]:
    playbook = bundle['playbook']
    worker_items = {item['key']: item for item in bundle['workers'] if isinstance(item, dict) and item.get('key')}
    tool_items = {item['key']: item for item in bundle['tools'] if isinstance(item, dict) and item.get('key')}
    eval_items = {item['key']: item for item in bundle['evals'] if isinstance(item, dict) and item.get('key')}
    capabilities = bundle.get('capabilities', {})

    issues: list[str] = []
    warnings: list[str] = []

    required_inputs = [str(item) for item in playbook.get('spec', {}).get('required_inputs', []) if item]
    missing_inputs = [key for key in required_inputs if key not in inputs]
    if missing_inputs:
        issues.append(f'missing required inputs: {missing_inputs}')

    allowed_workers = [str(item) for item in playbook.get('spec', {}).get('allowed_workers', []) if item]
    worker_rows: list[dict[str, Any]] = []
    hermes_required = False
    for key in allowed_workers:
        item = worker_items.get(key)
        if item is None:
            issues.append(f'missing worker registry item: {key}')
            continue
        worker_type = str(item.get('spec', {}).get('worker_type', 'unknown'))
        if worker_type == 'hermes_agent':
            hermes_required = True
        worker_rows.append({'key': key, 'status': item.get('status'), 'worker_type': worker_type})
        if item.get('status') != 'active':
            issues.append(f'worker is not active: {key}')

    allowed_tools = [str(item) for item in playbook.get('spec', {}).get('allowed_tools', []) if item]
    tool_rows: list[dict[str, Any]] = []
    for key in allowed_tools:
        item = tool_items.get(key)
        if item is None:
            issues.append(f'missing tool registry item: {key}')
            continue
        tool_rows.append({'key': key, 'status': item.get('status'), 'runtime_type': item.get('spec', {}).get('runtime_type')})
        if item.get('status') != 'active':
            issues.append(f'tool is not active: {key}')

    required_evals = [str(item) for item in playbook.get('spec', {}).get('required_eval_keys', []) if item]
    eval_rows: list[dict[str, Any]] = []
    for key in required_evals:
        item = eval_items.get(key)
        if item is None:
            issues.append(f'missing eval registry item: {key}')
            continue
        eval_rows.append({'key': key, 'status': item.get('status')})
        if item.get('status') != 'active':
            issues.append(f'eval is not active: {key}')

    provider_inputs = inputs.get('providers')
    for key in allowed_workers:
        item = worker_items.get(key)
        if item is None:
            continue
        capabilities_spec = item.get('spec', {}).get('provider_repair_policy', {}).get('provider_capabilities') or {}
        if not capabilities_spec or not isinstance(provider_inputs, list):
            continue
        requested = sorted({str(provider).lower() for provider in provider_inputs})
        supported = sorted(str(provider).lower() for provider in capabilities_spec.keys())
        unsupported = [provider for provider in requested if provider not in supported]
        if unsupported:
            issues.append(f'worker {key} does not support requested providers {unsupported}; supported providers: {supported}')

    hermes_capability = capabilities.get('hermes', {}) if isinstance(capabilities, dict) else {}
    if hermes_required and not hermes_capability.get('available'):
        issues.append('playbook requires Hermes workers but runtime capabilities report Hermes unavailable')
    if not hermes_required and not hermes_capability.get('available'):
        warnings.append('Hermes is unavailable, but this playbook does not require Hermes workers')

    summary = {
        'playbook_key': playbook.get('key'),
        'ready': not issues,
        'issue_count': len(issues),
        'warning_count': len(warnings),
        'required_inputs': required_inputs,
        'missing_inputs': missing_inputs,
        'worker_count': len(allowed_workers),
        'tool_count': len(allowed_tools),
        'eval_count': len(required_evals),
        'hermes_required': hermes_required,
        'hermes_available': bool(hermes_capability.get('available')),
        'goal_protocol': playbook.get('spec', {}).get('goal_protocol'),
    }
    return {
        'summary': summary,
        'playbook': playbook,
        'workers': worker_rows,
        'tools': tool_rows,
        'evals': eval_rows,
        'issues': issues,
        'warnings': warnings,
        'capabilities': capabilities,
    }


def render_readiness_markdown(report: dict[str, Any]) -> str:
    summary = report.get('summary', {})
    lines = [
        '# Playbook Readiness',
        '',
        f"- Playbook: `{summary.get('playbook_key', 'unknown')}`",
        f"- Ready: `{summary.get('ready', False)}`",
        f"- Goal protocol: `{summary.get('goal_protocol')}`",
        f"- Hermes required: `{summary.get('hermes_required', False)}`",
        f"- Hermes available: `{summary.get('hermes_available', False)}`",
        f"- Missing inputs: {summary.get('missing_inputs', [])}",
    ]
    lines.extend(['', '## Issues'])
    if report.get('issues'):
        for item in report['issues']:
            lines.append(f'- {item}')
    else:
        lines.append('- No blocking issue detected.')
    lines.extend(['', '## Warnings'])
    if report.get('warnings'):
        for item in report['warnings']:
            lines.append(f'- {item}')
    else:
        lines.append('- No warning detected.')
    lines.extend(['', '## Workers'])
    for item in report.get('workers', []):
        lines.append(f"- `{item.get('key')}` [{item.get('status')}] type=`{item.get('worker_type')}`")
    lines.extend(['', '## Tools'])
    for item in report.get('tools', []):
        lines.append(f"- `{item.get('key')}` [{item.get('status')}] runtime=`{item.get('runtime_type')}`")
    lines.extend(['', '## Evals'])
    for item in report.get('evals', []):
        lines.append(f"- `{item.get('key')}` [{item.get('status')}]")
    return '\n'.join(lines)


def create_run_payload(*, playbook_key: str, goal: str, inputs: dict[str, Any], require_human_approval: bool = True) -> dict[str, Any]:
    return {
        'playbook_key': playbook_key,
        'l2_mode': 'execution',
        'goal': goal,
        'inputs': inputs,
        'require_human_approval': require_human_approval,
    }


def wait_for_terminal_run(api_url: str, run_id: str, timeout_seconds: int) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    latest: dict[str, Any] | None = None
    while time.monotonic() < deadline:
        latest = request_json(f"{api_url.rstrip('/')}/runs/{run_id}")  # type: ignore[assignment]
        if not isinstance(latest, dict):
            raise RuntimeError(f'real run fetch returned invalid payload: {latest}')
        print(
            'poll',
            latest.get('status'),
            'tasks',
            len(latest.get('tasks', [])),
            'evals',
            len(latest.get('evals', [])),
            'events',
            len(latest.get('events', [])),
            'diagnosis',
            bool(latest.get('diagnosis')),
            'proposals',
            len(latest.get('improvement_proposals', [])),
            flush=True,
        )
        if latest.get('status') in TERMINAL_OR_BLOCKED:
            return latest
        time.sleep(5)
    raise RuntimeError(f'real run did not reach terminal-or-blocked state before timeout: {run_id}')


def validate_terminal_run(run: dict[str, Any], *, expected_statuses: set[str]) -> dict[str, Any]:
    status = str(run.get('status') or 'unknown')
    diagnosis = run.get('diagnosis') if isinstance(run.get('diagnosis'), dict) else None
    if status not in expected_statuses:
        raise RuntimeError(f'run ended in unexpected status={status} diagnosis={diagnosis}')
    if status == 'waiting_user' and isinstance(diagnosis, dict):
        if diagnosis.get('root_cause') not in {None, 'none'} or diagnosis.get('improvement_needed'):
            raise RuntimeError(f'waiting_user is only accepted for healthy human-gated runs: diagnosis={diagnosis}')
        if run.get('playbook_key') == 'goal-discovery':
            interaction = run.get('output', {}).get('interaction') if isinstance(run.get('output'), dict) else None
            if not isinstance(interaction, dict):
                raise RuntimeError('goal-discovery waiting_user output must include a structured interaction')
            options = interaction.get('options')
            if not isinstance(options, list) or len(options) < 2 or len(options) > 4:
                raise RuntimeError(f'goal-discovery interaction must include 2-4 options: {interaction}')
    if len(run.get('tasks', [])) < 1:
        raise RuntimeError('run reached terminal state without any real task')
    if len(run.get('events', [])) < 2:
        raise RuntimeError('run reached terminal state without enough runtime evidence')
    if isinstance(diagnosis, dict):
        evidence = diagnosis.get('evidence', [])
        if diagnosis.get('root_cause') not in {None, 'none'} and not evidence:
            raise RuntimeError('diagnosis has non-empty root cause but no recorded evidence')
    return {
        'run_id': run.get('id'),
        'status': status,
        'task_count': len(run.get('tasks', [])),
        'eval_count': len(run.get('evals', [])),
        'event_count': len(run.get('events', [])),
        'diagnosis': diagnosis,
        'improvement_proposals': run.get('improvement_proposals', []),
    }


def review_query_string(*, playbook_key: str | None = None, since_hours: int | None = None) -> str:
    params: dict[str, Any] = {}
    if playbook_key is not None:
        params['playbook_key'] = playbook_key
    if since_hours is not None:
        params['since_hours'] = since_hours
    return f"?{urlencode(params)}" if params else ''
