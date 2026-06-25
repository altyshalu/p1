import os

from l2l3_protocol.api.main import (
    _build_run_summary,
    _cors_allow_origins,
    _hydrate_runtime_env_from_dotenv,
    _is_operator_authorized,
    _p1_readiness_payload,
    app,
)
from l2l3_protocol.services.dashboard import operator_dashboard_html
from l2l3_protocol.services.p1_defaults import default_p1_inputs
from l2l3_protocol.core.schemas import ProcessRunCreate, RecentSystemReviewCreate
from pydantic import ValidationError


def test_generic_runtime_api_routes_are_registered() -> None:
    routes = {(route.path, ','.join(sorted(getattr(route, 'methods', set()) or []))) for route in app.routes}

    assert ('/runs', 'POST') in routes
    assert ('/runs', 'GET') in routes
    assert ('/p1/runs', 'POST') in routes
    assert ('/dashboard', 'GET') in routes
    assert ('/favicon.ico', 'GET') in routes
    assert ('/runs/{run_id}', 'GET') in routes
    assert ('/runs/{run_id}/summary', 'GET') in routes
    assert ('/runs/{run_id}/messages', 'POST') in routes
    assert ('/runs/{run_id}/control', 'POST') in routes
    assert ('/runs/{run_id}/events/stream', 'GET') in routes
    assert ('/improvement-proposals', 'GET') in routes
    assert ('/improvement-proposals/{proposal_id}/approve', 'POST') in routes
    assert ('/improvement-proposals/{proposal_id}/reject', 'POST') in routes
    assert ('/improvement-proposals/{proposal_id}/implement', 'POST') in routes
    assert ('/improvement-proposals/{proposal_id}/mark-implemented', 'POST') in routes
    assert ('/improvement-proposals/{proposal_id}/mark-proven', 'POST') in routes
    assert ('/failure-learnings', 'GET') in routes
    assert ('/system-reviews/recent', 'POST') in routes
    assert ('/system-reviews', 'GET') in routes
    assert ('/reports/system-learning', 'GET') in routes
    assert ('/regression-cases', 'GET') in routes
    assert ('/runtime/capabilities', 'GET') in routes
    assert ('/p1/readiness', 'GET') in routes


def test_p1_defaults_are_demo_target_and_write_gated() -> None:
    inputs = default_p1_inputs()

    assert inputs['mode'] == 'full_pipeline'
    assert inputs['limit'] == 20
    assert inputs['allow_google_sheet_write'] is True
    assert inputs['allow_outreach_master_write'] is True
    assert inputs['use_triage_cache'] is True
    assert inputs['verify_linkedin_live'] is True
    assert inputs['google_sheet_tab'] == 'P1_L2L3_NEW_LEADS'


def test_operator_auth_accepts_bearer_or_api_key_header() -> None:
    assert _is_operator_authorized({'authorization': 'Bearer secret'}, 'secret') is True
    assert _is_operator_authorized({'x-l2l3-api-key': 'secret'}, 'secret') is True
    assert _is_operator_authorized({'authorization': 'Bearer wrong'}, 'secret') is False


def test_p1_readiness_reports_missing_default_runtime_keys(monkeypatch) -> None:
    for key in [
        'GEMINI_API_KEY',
        'EXA_API_KEY',
        'APIFY_API_TOKEN',
        'GOOGLE_SA_PATH',
        'P1_GOOGLE_SHEET_ID',
        'P1_DOSSIER_OUTPUT_PATH',
        'P1_OUTREACH_MASTER_PATH',
    ]:
        monkeypatch.delenv(key, raising=False)

    report = _p1_readiness_payload()

    assert report['ready'] is False
    assert 'GEMINI_API_KEY' in report['missing_required_keys']
    assert 'EXA_API_KEY' in report['missing_required_keys']
    assert 'APIFY_API_TOKEN' in report['missing_required_keys']


def test_runtime_env_hydrates_from_dotenv_for_subprocess_workers(monkeypatch, tmp_path) -> None:
    env_path = tmp_path / '.env'
    env_path.write_text('EXA_API_KEY=from-env-file\nIGNORED_KEY=nope\n', encoding='utf-8')
    monkeypatch.delenv('EXA_API_KEY', raising=False)
    monkeypatch.delenv('IGNORED_KEY', raising=False)

    _hydrate_runtime_env_from_dotenv(env_path)

    assert os.environ['EXA_API_KEY'] == 'from-env-file'
    assert 'IGNORED_KEY' not in os.environ


def test_cors_origins_are_not_wildcard() -> None:
    assert '*' not in _cors_allow_origins()


def test_operator_dashboard_uses_real_api_endpoints() -> None:
    html = operator_dashboard_html()

    assert '/runs?playbook_key=p1-operator-outreach&limit=20' in html
    assert '/p1/runs' in html
    assert 'l2l3OperatorApiKey' in html
    assert 'authorization' in html
    assert '/reports/system-learning?playbook_key=p1-operator-outreach&since_hours=168' in html
    assert 'Source Quality' in html
    assert 'Runtime Bottlenecks' in html
    assert 'Gateway Rejections' in html
    assert 'source_quality_by_source' in html
    assert 'duration_by_worker_ms' in html
    assert 'triage_cache_hits' in html
    assert 'gateway_rejection_buckets' in html
    assert 'function renderGatewayRejections(gatewayRejectionBuckets)' in html
    assert 'metricKeys = ["raw_leads","normalized_leads","rejected_leads","triage_qualified","dossiers","gateway_approved","gateway_rejected","drafted","eval_passed","sheet_written","data_lake_written","outreach_master_written","provider_cache_hits","triage_cache_hits"]' in html
    assert '<td>${esc(reason)}</td><td>${esc(count)}</td>' in html
    assert 'function esc(value)' in html
    assert '<td>${esc(source)}</td>' in html
    assert '<tr><td>${esc(worker)}</td>' in html
    assert 'fake' not in html.lower()


def test_run_create_rejects_old_process_key_field() -> None:
    try:
        ProcessRunCreate(goal='x', process_key='old')
    except ValidationError as exc:
        assert 'Extra inputs are not permitted' in str(exc)
    else:
        raise AssertionError('process_key must not be accepted')


def test_recent_review_payload_accepts_optional_since_hours() -> None:
    payload = RecentSystemReviewCreate(limit=10, playbook_key='build-in-public', since_hours=24)

    assert payload.limit == 10
    assert payload.playbook_key == 'build-in-public'
    assert payload.since_hours == 24


def test_run_summary_builder_surfaces_dashboard_fields() -> None:
    summary = _build_run_summary(
        {
            'id': 'run-1',
            'status': 'waiting_approval',
            'playbook_key': 'p1-operator-outreach',
            'goal': 'prove p1',
            'output': {'metrics': {'drafted': 2}, 'approval_preview': {'rows': 2}, 'external_sync_requested': True},
            'artifacts': [{'artifact_type': 'p1_external_action_preview', 'payload': {'rows': 2}}],
            'tasks': [{'status': 'completed'}, {'status': 'failed'}],
            'evals': [{'eval_key': 'p1-outreach-draft-quality', 'passed': True}],
            'diagnosis': {'root_cause': 'none'},
        }
    )

    assert summary['status'] == 'waiting_approval'
    assert summary['latest_metrics']['drafted'] == 2
    assert summary['artifact_counts']['p1_external_action_preview'] == 1
    assert summary['task_status_counts']['completed'] == 1
    assert summary['latest_eval_results']['p1-outreach-draft-quality']['passed'] is True
    assert summary['pending_actions'][0]['type'] == 'approval'


def test_run_summary_builder_surfaces_waiting_user_pending_action() -> None:
    summary = _build_run_summary(
        {
            'id': 'run-2',
            'status': 'waiting_user',
            'playbook_key': 'goal-discovery',
            'goal': 'clarify goal',
            'output': {},
            'artifacts': [],
            'tasks': [],
            'evals': [],
            'diagnosis': None,
        }
    )

    assert summary['pending_actions'][0]['type'] == 'user_input'


def test_run_summary_builder_surfaces_failed_run_without_pending_actions() -> None:
    summary = _build_run_summary(
        {
            'id': 'run-3',
            'status': 'failed',
            'playbook_key': 'p1-operator-outreach',
            'goal': 'prove p1',
            'output': {'metrics': {'drafted': 0}},
            'artifacts': [],
            'tasks': [{'status': 'failed'}],
            'evals': [],
            'diagnosis': {'root_cause': 'bad_or_missing_input'},
        }
    )

    assert summary['latest_diagnosis']['root_cause'] == 'bad_or_missing_input'
    assert summary['pending_actions'] == []
