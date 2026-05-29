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

from p1_real_common import approve_run, assert_status, assert_summary_shape, create_run, get_summary, load_inputs, require_capabilities, require_health, wait_for_run


def verify_sheet_rows(spreadsheet_id: str, tab_name: str, service_account_path: str, expected_lead_ids: list[str]) -> dict[str, int]:
    from l2l3_protocol.workers.p1_operator_worker import _google_access_token, _request_json

    token = _google_access_token(service_account_path)
    payload = _request_json(
        f'https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{tab_name}!A:O'.replace(' ', '%20'),
        token=token,
    )
    values = payload.get('values', []) if isinstance(payload, dict) else []
    if not values:
        raise SystemExit('sheet verification failed: target tab returned no values')
    header = values[0]
    if 'lead_id' not in header:
        raise SystemExit(f'sheet verification failed: header has no lead_id column: {header}')
    lead_idx = header.index('lead_id')
    present = {str(row[lead_idx]).strip() for row in values[1:] if len(row) > lead_idx}
    missing = [lead_id for lead_id in expected_lead_ids if lead_id not in present]
    if missing:
        raise SystemExit(f'sheet verification failed: expected lead_ids are missing from sheet: {missing}')
    return {'row_count': len(values) - 1, 'matched_leads': len(expected_lead_ids)}


def verify_outreach_master(path_value: str, expected_pairs: list[tuple[str, str]]) -> dict[str, int]:
    path = Path(path_value)
    if not path.exists():
        raise SystemExit(f'outreach master verification failed: file does not exist: {path}')
    payload = json.loads(path.read_text(encoding='utf-8'))
    if isinstance(payload, list):
        drafts = payload
    elif isinstance(payload, dict):
        drafts = payload.get('drafts', [])
    else:
        raise SystemExit(f'outreach master verification failed: unsupported JSON payload at {path}')
    if not isinstance(drafts, list):
        raise SystemExit('outreach master verification failed: drafts must be a list')
    present = {
        (str(item.get('run_id') or '').strip(), str(item.get('lead_id') or '').strip())
        for item in drafts
        if isinstance(item, dict)
    }
    missing = [pair for pair in expected_pairs if pair not in present]
    if missing:
        raise SystemExit(f'outreach master verification failed: expected run_id/lead_id pairs are missing: {missing}')
    return {'draft_count': len(drafts), 'matched_pairs': len(expected_pairs)}


def verify_data_lake(root_value: str, expected_lead_ids: list[str]) -> dict[str, int]:
    root = Path(root_value)
    if not root.exists() or not root.is_dir():
        raise SystemExit(f'data lake verification failed: directory does not exist: {root}')
    missing: list[str] = []
    for lead_id in expected_lead_ids:
        path = root / f'{lead_id}.json'
        if not path.exists():
            missing.append(lead_id)
    if missing:
        raise SystemExit(f'data lake verification failed: expected dossier files are missing: {missing}')
    return {'matched_files': len(expected_lead_ids)}


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a real full P1 proof with health/capabilities/summary verification.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--goal', default='Run the full real P1 operator outreach proof.')
    parser.add_argument('--inputs-json', required=True)
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    parser.add_argument('--approve', action='store_true', help='Approve external writes if the run stops at waiting_approval')
    parser.add_argument('--verify-sheet', action='store_true')
    parser.add_argument('--verify-outreach-master', action='store_true')
    parser.add_argument('--verify-data-lake', action='store_true')
    parser.add_argument('--google-service-account-path')
    args = parser.parse_args()

    inputs = load_inputs(args.inputs_json)
    require_health(args.base_url)
    capabilities = require_capabilities(args.base_url)
    created = create_run(args.base_url, args.goal, inputs)
    run = wait_for_run(args.base_url, created['id'], args.timeout_seconds)
    summary = get_summary(args.base_url, created['id'])
    assert_summary_shape(summary)

    final_run = run
    if run['status'] == 'waiting_approval' and args.approve:
        approve_run(args.base_url, created['id'])
        final_run = wait_for_run(args.base_url, created['id'], args.timeout_seconds)
        summary = get_summary(args.base_url, created['id'])
        assert_summary_shape(summary)

    assert_status(final_run, {'completed', 'waiting_approval', 'waiting_user'})
    latest_metrics = summary.get('latest_metrics', {}) if isinstance(summary.get('latest_metrics'), dict) else {}
    if final_run['status'] == 'completed' and not latest_metrics:
        raise SystemExit('full proof failed: completed run has empty latest_metrics')

    sheet_verification = None
    outreach_master_verification = None
    data_lake_verification = None
    preview = summary.get('latest_approval_preview', {}) if isinstance(summary.get('latest_approval_preview'), dict) else {}
    if args.verify_sheet and final_run['status'] == 'completed':
        spreadsheet_id = str((preview.get('google_sheets') or {}).get('spreadsheet_id') or inputs.get('spreadsheet_id') or '')
        tab_name = str((preview.get('google_sheets') or {}).get('tab_name') or inputs.get('google_sheet_tab') or 'P1_L2L3_NEW_LEADS')
        service_account_path = args.google_service_account_path or inputs.get('google_service_account_path')
        if not spreadsheet_id or not service_account_path:
            raise SystemExit('verify-sheet requires spreadsheet_id and google_service_account_path')
        lead_ids = [str(row.get('lead_id')) for row in (preview.get('google_sheets') or {}).get('rows', []) if isinstance(row, dict) and row.get('lead_id')]
        if not lead_ids:
            raise SystemExit('verify-sheet requested but preview did not include any lead_ids to validate')
        sheet_verification = verify_sheet_rows(spreadsheet_id, tab_name, str(service_account_path), lead_ids)

    if args.verify_outreach_master and final_run['status'] == 'completed':
        outreach_master_path = str((preview.get('outreach_master') or {}).get('path') or inputs.get('outreach_master_path') or '')
        rows = (preview.get('outreach_master') or {}).get('entries', []) if isinstance(preview.get('outreach_master'), dict) else []
        pairs = [
            (str(row.get('run_id')).strip(), str(row.get('lead_id')).strip())
            for row in rows
            if isinstance(row, dict) and row.get('run_id') and row.get('lead_id')
        ]
        if not outreach_master_path:
            raise SystemExit('verify-outreach-master requires outreach_master_path')
        if not pairs:
            raise SystemExit('verify-outreach-master requested but preview did not include any run_id/lead_id pairs')
        outreach_master_verification = verify_outreach_master(outreach_master_path, pairs)

    if args.verify_data_lake and final_run['status'] == 'completed':
        data_lake_path = str((preview.get('data_lake') or {}).get('path') or inputs.get('data_lake_dossier_path') or inputs.get('dossier_output_path') or '')
        files = (preview.get('data_lake') or {}).get('files', []) if isinstance(preview.get('data_lake'), dict) else []
        lead_ids = [str(item.get('lead_id')).strip() for item in files if isinstance(item, dict) and item.get('lead_id')]
        if not data_lake_path:
            raise SystemExit('verify-data-lake requires data_lake_dossier_path or dossier_output_path')
        if not lead_ids:
            raise SystemExit('verify-data-lake requested but preview did not include any lead_ids to validate')
        data_lake_verification = verify_data_lake(data_lake_path, lead_ids)

    report = {
        'run_id': created['id'],
        'status': final_run['status'],
        'health': 'ok',
        'capabilities': capabilities,
        'summary_status': summary.get('status'),
        'latest_metrics': latest_metrics,
        'pending_actions': summary.get('pending_actions'),
        'sheet_verification': sheet_verification,
        'outreach_master_verification': outreach_master_verification,
        'data_lake_verification': data_lake_verification,
        'diagnosis': final_run.get('diagnosis'),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
