from l2l3_protocol.api.main import app
from l2l3_protocol.core.schemas import ProcessRunCreate, RecentSystemReviewCreate
from pydantic import ValidationError


def test_generic_runtime_api_routes_are_registered() -> None:
    routes = {(route.path, ','.join(sorted(getattr(route, 'methods', set()) or []))) for route in app.routes}

    assert ('/runs', 'POST') in routes
    assert ('/runs/{run_id}', 'GET') in routes
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
