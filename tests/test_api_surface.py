from l2l3_protocol.api.main import _build_run_summary, app
from l2l3_protocol.core.schemas import ProcessRunCreate, RecentSystemReviewCreate
from pydantic import ValidationError


def test_generic_runtime_api_routes_are_registered() -> None:
    routes = {(route.path, ','.join(sorted(getattr(route, 'methods', set()) or []))) for route in app.routes}

    assert ('/runs', 'POST') in routes
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
