#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from p1_real_common import request_json, require_capabilities, require_health

REQUIRED_KEYS_BY_MODE = {
    'existing_dossiers': ['GEMINI_API_KEY', 'EXA_API_KEY'],
    'source_only': ['GEMINI_API_KEY', 'APIFY_API_TOKEN'],
    'full_pipeline': ['GEMINI_API_KEY', 'APIFY_API_TOKEN'],
}
OPTIONAL_WRITE_KEYS = {
    'allow_google_sheet_write': ['GOOGLE_SA_PATH', 'P1_GOOGLE_SHEET_ID'],
    'allow_outreach_master_write': ['P1_OUTREACH_MASTER_PATH'],
    'allow_data_lake_write': ['P1_DOSSIER_OUTPUT_PATH'],
}


def load_env_map(path: str) -> dict[str, str]:
    env_path = Path(path)
    if not env_path.exists():
        raise SystemExit(f'env file not found: {env_path}')
    values: dict[str, str] = {}
    for line in env_path.read_text(encoding='utf-8').splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith('#') or '=' not in stripped:
            continue
        key, value = stripped.split('=', 1)
        values[key.strip()] = value.strip()
    return values


def require_hub_seed(base_url: str, sync_yaml: bool) -> dict[str, object]:
    if sync_yaml:
        sync_result = request_json(f'{base_url}/hub/sync/yaml', method='POST')
    else:
        sync_result = {'synced': None}
    playbook = request_json(f'{base_url}/hub/playbook/p1-operator-outreach')
    worker = request_json(f'{base_url}/hub/worker/p1-source-merger')
    eval_spec = request_json(f'{base_url}/hub/eval/p1-outreach-draft-quality')
    tool = request_json(f'{base_url}/hub/tool/apify-actor-tool')
    return {
        'sync': sync_result,
        'playbook_key': playbook.get('key'),
        'worker_key': worker.get('key'),
        'eval_key': eval_spec.get('key'),
        'tool_key': tool.get('key'),
    }


def _non_empty_string(value: Any) -> str:
    return str(value).strip() if isinstance(value, str) and value.strip() else ''


def _resolve_string(inputs: dict[str, object], env_map: dict[str, str], input_keys: list[str], env_keys: list[str]) -> str:
    for key in input_keys:
        value = _non_empty_string(inputs.get(key))
        if value:
            return value
    for key in env_keys:
        value = _non_empty_string(env_map.get(key))
        if value:
            return value
    return ''


def _check_path(path_value: str, *, expect_dir: bool | None = None) -> bool:
    path = Path(path_value)
    if not path.exists():
        return False
    if expect_dir is True:
        return path.is_dir()
    if expect_dir is False:
        return path.is_file()
    return True


def validate_runtime_inputs(mode: str, inputs: dict[str, object], env_map: dict[str, str], *, explicit_inputs_supplied: bool) -> tuple[list[str], dict[str, bool], dict[str, object]]:
    missing: list[str] = []
    path_checks: dict[str, bool] = {}
    resolved: dict[str, object] = {}

    if explicit_inputs_supplied:
        input_mode = _non_empty_string(inputs.get('mode'))
        if not input_mode:
            missing.append('mode')
        elif input_mode != mode:
            missing.append(f'mode (must equal {mode})')
        else:
            resolved['mode'] = input_mode

    if mode == 'existing_dossiers':
        dossier_source = _resolve_string(inputs, env_map, ['dossier_source_path'], ['P1_DOSSIER_SOURCE_PATH'])
        if not dossier_source:
            missing.append('dossier_source_path or P1_DOSSIER_SOURCE_PATH')
        else:
            resolved['dossier_source_path'] = dossier_source
            path_checks['dossier_source_path'] = _check_path(dossier_source, expect_dir=True)
    else:
        sources = inputs.get('sources')
        if explicit_inputs_supplied and (not isinstance(sources, list) or not [item for item in sources if str(item).strip()]):
            missing.append('sources')
        elif isinstance(sources, list) and [item for item in sources if str(item).strip()]:
            resolved['sources'] = [str(item).strip() for item in sources if str(item).strip()]

    if bool(inputs.get('allow_google_sheet_write')):
        spreadsheet_id = _resolve_string(inputs, env_map, ['spreadsheet_id'], ['P1_GOOGLE_SHEET_ID'])
        if not spreadsheet_id:
            missing.append('spreadsheet_id or P1_GOOGLE_SHEET_ID')
        else:
            resolved['spreadsheet_id'] = spreadsheet_id
        tab_name = inputs.get('google_sheet_tab')
        if tab_name is not None and not _non_empty_string(tab_name):
            missing.append('google_sheet_tab')
        service_account_path = _resolve_string(inputs, env_map, ['google_service_account_path'], ['GOOGLE_SA_PATH'])
        if not service_account_path:
            missing.append('google_service_account_path or GOOGLE_SA_PATH')
        else:
            resolved['google_service_account_path'] = service_account_path
            path_checks['google_service_account_path'] = _check_path(service_account_path, expect_dir=False)

    if bool(inputs.get('allow_outreach_master_write')):
        outreach_master_path = _resolve_string(inputs, env_map, ['outreach_master_path'], ['P1_OUTREACH_MASTER_PATH'])
        if not outreach_master_path:
            missing.append('outreach_master_path or P1_OUTREACH_MASTER_PATH')
        else:
            resolved['outreach_master_path'] = outreach_master_path

    if bool(inputs.get('allow_data_lake_write')):
        data_lake_path = _resolve_string(
            inputs,
            env_map,
            ['data_lake_dossier_path', 'dossier_output_path'],
            ['P1_DOSSIER_OUTPUT_PATH', 'P1_DOSSIER_SOURCE_PATH'],
        )
        if not data_lake_path:
            missing.append('data_lake_dossier_path or dossier_output_path or P1_DOSSIER_OUTPUT_PATH')
        else:
            resolved['data_lake_dossier_path'] = data_lake_path

    deduped_missing = list(dict.fromkeys(missing))
    return deduped_missing, path_checks, resolved


def readiness_report(
    base_url: str,
    env_file: str,
    mode: str,
    inputs: dict[str, object],
    sync_yaml: bool,
    *,
    explicit_inputs_supplied: bool = False,
) -> dict[str, object]:
    health = require_health(base_url)
    capabilities = require_capabilities(base_url)
    hub = require_hub_seed(base_url, sync_yaml)
    env_map = load_env_map(env_file)

    required_keys = list(REQUIRED_KEYS_BY_MODE[mode])
    for flag, keys in OPTIONAL_WRITE_KEYS.items():
        if bool(inputs.get(flag)):
            required_keys.extend(keys)
    missing_required_keys = sorted({key for key in required_keys if not env_map.get(key)})

    missing_runtime_inputs, path_checks, resolved_inputs = validate_runtime_inputs(
        mode,
        inputs,
        env_map,
        explicit_inputs_supplied=explicit_inputs_supplied,
    )

    return {
        'mode': mode,
        'health': health,
        'capabilities': capabilities,
        'hub': hub,
        'required_keys': required_keys,
        'missing_required_keys': missing_required_keys,
        'missing_runtime_inputs': missing_runtime_inputs,
        'resolved_inputs': resolved_inputs,
        'path_checks': path_checks,
        'ready': not missing_required_keys and not missing_runtime_inputs and all(path_checks.values() or [True]),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a real P1 backend readiness preflight.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--env-file', default='.env')
    parser.add_argument('--mode', choices=sorted(REQUIRED_KEYS_BY_MODE), default='full_pipeline')
    parser.add_argument('--inputs-json', help='Optional inputs JSON to detect write-path requirements.')
    parser.add_argument('--skip-sync-yaml', action='store_true')
    args = parser.parse_args()

    inputs: dict[str, object] = {}
    explicit_inputs_supplied = bool(args.inputs_json)
    if args.inputs_json:
        payload = json.loads(Path(args.inputs_json).read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise SystemExit('inputs-json must contain a JSON object')
        inputs = payload

    report = readiness_report(
        args.base_url,
        args.env_file,
        args.mode,
        inputs,
        not args.skip_sync_yaml,
        explicit_inputs_supplied=explicit_inputs_supplied,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
