#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
sys.path.insert(0, str(ROOT / "scripts"))

from p1_real_common import approve_run, assert_status, assert_summary_shape, create_run, get_summary, load_inputs, require_capabilities, require_health, wait_for_run


LINKEDIN_PERSON_RE = re.compile(r"^https?://(?:(?:www|[a-z]{2})\.)?linkedin\.com/in/[A-Za-z0-9%_\-]+$", re.IGNORECASE)


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


def verify_sheet_rows(spreadsheet_id: str, tab_name: str, service_account_path: str, expected_pairs: list[tuple[str, str]]) -> dict[str, int]:
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
    if 'run_id' not in header or 'lead_id' not in header:
        raise SystemExit(f'sheet verification failed: header has no run_id/lead_id columns: {header}')
    run_idx = header.index('run_id')
    lead_idx = header.index('lead_id')
    present = {
        (str(row[run_idx]).strip(), str(row[lead_idx]).strip())
        for row in values[1:]
        if len(row) > max(run_idx, lead_idx)
    }
    missing = [pair for pair in expected_pairs if pair not in present]
    if missing:
        raise SystemExit(f'sheet verification failed: expected run_id/lead_id pairs are missing from sheet: {missing}')
    return {'row_count': len(values) - 1, 'matched_pairs': len(expected_pairs)}


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


def artifact_payloads(run: dict[str, Any], artifact_type: str) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    for artifact in run.get('artifacts', []):
        if not isinstance(artifact, dict) or artifact.get('artifact_type') != artifact_type:
            continue
        payload = artifact.get('payload')
        if isinstance(payload, dict):
            payloads.append(payload)
    return payloads


def sheet_verification_config(preview: dict[str, Any], inputs: dict[str, Any], google_service_account_path: str | None) -> dict[str, str]:
    spreadsheet_id = str(
        (preview.get('google_sheets') or {}).get('spreadsheet_id')
        or inputs.get('spreadsheet_id')
        or os.environ.get('P1_GOOGLE_SHEET_ID')
        or ''
    )
    tab_name = str((preview.get('google_sheets') or {}).get('tab_name') or inputs.get('google_sheet_tab') or 'P1_L2L3_NEW_LEADS')
    service_account_path = str(
        google_service_account_path
        or inputs.get('google_service_account_path')
        or os.environ.get('GOOGLE_SA_PATH')
        or ''
    )
    return {'spreadsheet_id': spreadsheet_id, 'tab_name': tab_name, 'service_account_path': service_account_path}


def outreach_master_path(preview: dict[str, Any], inputs: dict[str, Any]) -> str:
    return str(
        (preview.get('outreach_master') or {}).get('path')
        or inputs.get('outreach_master_path')
        or os.environ.get('P1_OUTREACH_MASTER_PATH')
        or ''
    )


def data_lake_path(preview: dict[str, Any], inputs: dict[str, Any]) -> str:
    return str(
        (preview.get('data_lake') or {}).get('path')
        or inputs.get('data_lake_dossier_path')
        or inputs.get('dossier_output_path')
        or os.environ.get('P1_DOSSIER_OUTPUT_PATH')
        or ''
    )


def expected_draft_lead_ids(run: dict[str, Any]) -> list[str]:
    lead_ids: list[str] = []
    for payload in artifact_payloads(run, 'p1_outreach_drafts'):
        drafts = payload.get('outreach_drafts', [])
        if not isinstance(drafts, list):
            continue
        for draft in drafts:
            if isinstance(draft, dict) and draft.get('lead_id'):
                lead_ids.append(str(draft['lead_id']).strip())
    return sorted({lead_id for lead_id in lead_ids if lead_id})


def expected_draft_pairs(run: dict[str, Any]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for payload in artifact_payloads(run, 'p1_outreach_drafts'):
        drafts = payload.get('outreach_drafts', [])
        if not isinstance(drafts, list):
            continue
        for draft in drafts:
            if isinstance(draft, dict) and draft.get('run_id') and draft.get('lead_id'):
                pairs.append((str(draft['run_id']).strip(), str(draft['lead_id']).strip()))
    return sorted({pair for pair in pairs if pair[0] and pair[1]})


def expected_dossier_lead_ids(run: dict[str, Any]) -> list[str]:
    lead_ids: list[str] = []
    for payload in artifact_payloads(run, 'p1_dossiers'):
        dossiers = payload.get('p1_dossiers', [])
        if not isinstance(dossiers, list):
            continue
        for dossier in dossiers:
            identity = dossier.get('identity') if isinstance(dossier, dict) else None
            if isinstance(identity, dict) and identity.get('lead_id'):
                lead_ids.append(str(identity['lead_id']).strip())
    return sorted({lead_id for lead_id in lead_ids if lead_id})


def verify_p1_quality(run: dict[str, Any]) -> dict[str, int]:
    gateway_items: list[dict[str, Any]] = []
    for payload in artifact_payloads(run, 'p1_gateway_evaluations'):
        items = payload.get('gateway_evaluations', [])
        if isinstance(items, list):
            gateway_items.extend(item for item in items if isinstance(item, dict))
    approved = [item for item in gateway_items if isinstance(item.get('gateway'), dict) and item['gateway'].get('decision') == 'awaiting_outreach']
    failures: list[str] = []
    for item in approved:
        gateway = item['gateway']
        name = str((item.get('dossier') or {}).get('identity', {}).get('name') or 'unknown')
        if int(gateway.get('identity_confidence') or 0) < 90:
            failures.append(f'{name}: identity_confidence_below_90')
        for key in ('product_b2c_fit', 'product_leadership_fit', 'verified_investor_fit'):
            if str(gateway.get(key)).upper() != 'PASS':
                failures.append(f'{name}: {key}_not_pass')
        if str(gateway.get('bandwidth_signal')).upper() != 'HIGH':
            failures.append(f'{name}: bandwidth_not_high')
        if str(gateway.get('liquidity_signal')).upper() != 'YES':
            failures.append(f'{name}: liquidity_not_yes')
        if str(gateway.get('exclusion_signal')).upper() == 'YES':
            failures.append(f'{name}: exclusion_signal_yes')
        if not isinstance(gateway.get('evidence_urls'), list) or not gateway['evidence_urls']:
            failures.append(f'{name}: missing_gateway_evidence_urls')
    if not approved:
        failures.append('no_gateway_approved_leads')

    draft_items: list[dict[str, Any]] = []
    for payload in artifact_payloads(run, 'p1_outreach_drafts'):
        items = payload.get('outreach_drafts', [])
        if isinstance(items, list):
            draft_items.extend(item for item in items if isinstance(item, dict))
    for draft in draft_items:
        name = str(draft.get('name') or 'unknown')
        text = str(draft.get('text') or '').strip()
        if not text:
            failures.append(f'{name}: missing_draft_text')
        if text and not has_clear_cta(text):
            failures.append(f'{name}: missing_clear_cta')
        if meeting_cta_count(text) > 1:
            failures.append(f'{name}: duplicate_meeting_cta')
        if draft.get('publish') is True:
            failures.append(f'{name}: draft_publish_true')
        if str(draft.get('status') or '') != 'draft':
            failures.append(f'{name}: draft_status_not_draft')
        linkedin_url = str(draft.get('linkedin_url') or '').strip().split('?')[0].rstrip('/')
        if not LINKEDIN_PERSON_RE.match(linkedin_url):
            failures.append(f'{name}: missing_verified_person_linkedin')
        if str(draft.get('identity_status') or '').strip() != 'verified_linkedin':
            failures.append(f'{name}: identity_status_not_verified')
        if not isinstance(draft.get('evidence_urls'), list) or not draft['evidence_urls']:
            failures.append(f'{name}: missing_draft_evidence_urls')
        claims = draft.get('claims')
        if not isinstance(claims, list) or not claims:
            failures.append(f'{name}: missing_claims')
        elif any(not isinstance(claim, dict) or not claim.get('source_url') for claim in claims):
            failures.append(f'{name}: ungrounded_claim')
    if approved and len(draft_items) < len(approved):
        failures.append(f'draft_count_below_approved_count:{len(draft_items)}<{len(approved)}')
    if failures:
        raise SystemExit(f'P1 quality verification failed: {failures}')
    return {'gateway_approved': len(approved), 'drafts_verified': len(draft_items)}


def has_clear_cta(text: str) -> bool:
    return meeting_cta_count(text) == 1


def meeting_cta_count(text: str) -> int:
    normalized = re.sub(r'\s+', ' ', text.strip().lower())
    meeting_action_re = re.compile(r'\b(call|chat|connect|meet|meeting|conversation)\b')
    timing_re = re.compile(r'\b(next week|30\s*[- ]?minutes?|30\s*min|quick|brief)\b')
    count = 0
    for sentence_match in re.finditer(r'[^.!?\n]+', normalized):
        sentence = sentence_match.group(0)
        for action_match in meeting_action_re.finditer(sentence):
            start, end = action_match.span()
            local_window = sentence[max(0, start - 50) : min(len(sentence), end + 80)]
            if timing_re.search(local_window):
                count += 1
    return count


def main() -> int:
    parser = argparse.ArgumentParser(description='Run a real full P1 proof with health/capabilities/summary verification.')
    parser.add_argument('--base-url', default='http://127.0.0.1:8000')
    parser.add_argument('--goal', default='Run the full real P1 operator outreach proof.')
    parser.add_argument('--inputs-json', required=True)
    parser.add_argument('--env-file')
    parser.add_argument('--timeout-seconds', type=int, default=1800)
    parser.add_argument('--approve', action='store_true', help='Approve external writes if the run stops at waiting_approval')
    parser.add_argument('--verify-sheet', action='store_true')
    parser.add_argument('--verify-outreach-master', action='store_true')
    parser.add_argument('--verify-data-lake', action='store_true')
    parser.add_argument('--verify-quality', action='store_true')
    parser.add_argument('--google-service-account-path')
    args = parser.parse_args()

    load_env_file(args.env_file)
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
    external_writes_requested = any(bool(inputs.get(key)) for key in ('allow_google_sheet_write', 'allow_outreach_master_write', 'allow_data_lake_write'))
    if external_writes_requested and final_run['status'] == 'waiting_approval':
        raise SystemExit('full proof incomplete: external writes were requested but run is still waiting_approval; rerun with --approve and verification flags')
    if final_run['status'] == 'completed':
        missing_verify_flags: list[str] = []
        if bool(inputs.get('allow_google_sheet_write')) and not args.verify_sheet:
            missing_verify_flags.append('--verify-sheet')
        if bool(inputs.get('allow_outreach_master_write')) and not args.verify_outreach_master:
            missing_verify_flags.append('--verify-outreach-master')
        if bool(inputs.get('allow_data_lake_write')) and not args.verify_data_lake:
            missing_verify_flags.append('--verify-data-lake')
        if missing_verify_flags:
            raise SystemExit(f'full proof incomplete: missing verification flags for requested external writes: {missing_verify_flags}')
    latest_metrics = summary.get('latest_metrics', {}) if isinstance(summary.get('latest_metrics'), dict) else {}
    if final_run['status'] == 'completed' and not latest_metrics:
        raise SystemExit('full proof failed: completed run has empty latest_metrics')

    sheet_verification = None
    outreach_master_verification = None
    data_lake_verification = None
    quality_verification = None
    preview = summary.get('latest_approval_preview', {}) if isinstance(summary.get('latest_approval_preview'), dict) else {}
    if args.verify_sheet and final_run['status'] == 'completed':
        sheet_config = sheet_verification_config(preview, inputs, args.google_service_account_path)
        spreadsheet_id = sheet_config['spreadsheet_id']
        tab_name = sheet_config['tab_name']
        service_account_path = sheet_config['service_account_path']
        if not spreadsheet_id or not service_account_path:
            raise SystemExit('verify-sheet requires spreadsheet_id and google_service_account_path')
        sheet_pairs = [
            (str(row.get('run_id')).strip(), str(row.get('lead_id')).strip())
            for row in (preview.get('google_sheets') or {}).get('rows', [])
            if isinstance(row, dict) and row.get('run_id') and row.get('lead_id')
        ]
        if not sheet_pairs:
            sheet_pairs = expected_draft_pairs(final_run)
        if not sheet_pairs:
            raise SystemExit('verify-sheet requested but run did not include any expected run_id/lead_id pairs to validate')
        sheet_verification = verify_sheet_rows(spreadsheet_id, tab_name, str(service_account_path), sheet_pairs)

    if args.verify_outreach_master and final_run['status'] == 'completed':
        outreach_master_path_value = outreach_master_path(preview, inputs)
        rows = (preview.get('outreach_master') or {}).get('entries', []) if isinstance(preview.get('outreach_master'), dict) else []
        pairs = [
            (str(row.get('run_id')).strip(), str(row.get('lead_id')).strip())
            for row in rows
            if isinstance(row, dict) and row.get('run_id') and row.get('lead_id')
        ]
        if not pairs:
            pairs = expected_draft_pairs(final_run)
        if not outreach_master_path_value:
            raise SystemExit('verify-outreach-master requires outreach_master_path')
        if not pairs:
            raise SystemExit('verify-outreach-master requested but run did not include any expected run_id/lead_id pairs')
        outreach_master_verification = verify_outreach_master(outreach_master_path_value, pairs)

    if args.verify_data_lake and final_run['status'] == 'completed':
        data_lake_path_value = data_lake_path(preview, inputs)
        files = (preview.get('data_lake') or {}).get('files', []) if isinstance(preview.get('data_lake'), dict) else []
        lead_ids = [str(item.get('lead_id')).strip() for item in files if isinstance(item, dict) and item.get('lead_id')]
        if not lead_ids:
            lead_ids = expected_dossier_lead_ids(final_run)
        if not data_lake_path_value:
            raise SystemExit('verify-data-lake requires data_lake_dossier_path or dossier_output_path')
        if not lead_ids:
            raise SystemExit('verify-data-lake requested but run did not include any expected lead_ids to validate')
        data_lake_verification = verify_data_lake(data_lake_path_value, lead_ids)

    if args.verify_quality:
        quality_verification = verify_p1_quality(final_run)

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
        'quality_verification': quality_verification,
        'diagnosis': final_run.get('diagnosis'),
    }
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
