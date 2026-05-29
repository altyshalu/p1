#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from p1_real_common import request_json, require_capabilities, require_health

REQUIRED_KEYS_BY_MODE = {
    'existing_dossiers': ['GEMINI_API_KEY', 'EXA_API_KEY', 'P1_DOSSIER_SOURCE_PATH'],
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


def readiness_report(base_url: str, env_file: str, mode: str, inputs: dict[str, object], sync_yaml: bool) -> dict[str, object]:
    health = require_health(base_url)
    capabilities = require_capabilities(base_url)
    hub = require_hub_seed(base_url, sync_yaml)
    env_map = load_env_map(env_file)

    required_keys = list(REQUIRED_KEYS_BY_MODE[mode])
    for flag, keys in OPTIONAL_WRITE_KEYS.items():
        if bool(inputs.get(flag)):
            required_keys.extend(keys)
    missing = sorted({key for key in required_keys if not env_map.get(key)})

    path_checks: dict[str, bool] = {}
    for key in ('GOOGLE_SA_PATH', 'P1_DOSSIER_SOURCE_PATH', 'P1_DOSSIER_OUTPUT_PATH', 'P1_OUTREACH_MASTER_PATH'):
        value = env_map.get(key)
        if not value:
            continue
        path_checks[key] = Path(value).exists()

    return {
        'mode': mode,
        'health': health,
        'capabilities': capabilities,
        'hub': hub,
        'required_keys': required_keys,
        'missing_required_keys': missing,
        'path_checks': path_checks,
        'ready': not missing and all(path_checks.values() or [True]),
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
    if args.inputs_json:
        payload = json.loads(Path(args.inputs_json).read_text(encoding='utf-8'))
        if not isinstance(payload, dict):
            raise SystemExit('inputs-json must contain a JSON object')
        inputs = payload

    report = readiness_report(args.base_url, args.env_file, args.mode, inputs, not args.skip_sync_yaml)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report['ready'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
