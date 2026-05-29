import importlib.util
from pathlib import Path


def _load(name: str, filename: str):
    script_path = Path(__file__).resolve().parents[1] / 'scripts' / filename
    spec = importlib.util.spec_from_file_location(name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_readiness_detects_missing_required_inputs() -> None:
    common = _load('real_playbook_common', 'real_playbook_common.py')
    report = common.assess_playbook_readiness(
        {
            'playbook': {'key': 'build-in-public', 'spec': {'required_inputs': ['signals', 'channels'], 'allowed_workers': [], 'allowed_tools': []}},
            'workers': [],
            'tools': [],
            'evals': [],
            'capabilities': {'hermes': {'available': True}},
        },
        inputs={'signals': ['one']},
    )

    assert report['summary']['ready'] is False
    assert report['summary']['missing_inputs'] == ['channels']


def test_readiness_requires_hermes_for_hermes_workers() -> None:
    common = _load('real_playbook_common', 'real_playbook_common.py')
    report = common.assess_playbook_readiness(
        {
            'playbook': {'key': 'build-in-public', 'spec': {'required_inputs': ['signals'], 'allowed_workers': ['narrative-synthesizer'], 'allowed_tools': []}},
            'workers': [{'key': 'narrative-synthesizer', 'status': 'active', 'spec': {'worker_type': 'hermes_agent'}}],
            'tools': [],
            'evals': [],
            'capabilities': {'hermes': {'available': False}},
        },
        inputs={'signals': ['one']},
    )

    assert report['summary']['hermes_required'] is True
    assert any('Hermes unavailable' in item or 'Hermes workers' in item for item in report['issues'])


def test_readiness_exposes_goal_protocol_summary() -> None:
    common = _load('real_playbook_common', 'real_playbook_common.py')
    report = common.assess_playbook_readiness(
        {
            'playbook': {'key': 'goal-discovery', 'spec': {'required_inputs': [], 'allowed_workers': ['goal-hypothesis-generator'], 'allowed_tools': [], 'goal_protocol': 'unclear_goal'}},
            'workers': [{'key': 'goal-hypothesis-generator', 'status': 'active', 'spec': {'worker_type': 'hermes_agent'}}],
            'tools': [],
            'evals': [],
            'capabilities': {'hermes': {'available': True}},
        },
        inputs={'context': ['vague request']},
    )

    assert report['summary']['ready'] is True
    assert report['summary']['goal_protocol'] == 'unclear_goal'


def test_acceptance_validator_rejects_failed_status() -> None:
    common = _load('real_playbook_common', 'real_playbook_common.py')
    try:
        common.validate_terminal_run(
            {
                'id': 'run-1',
                'status': 'failed',
                'tasks': [{'id': 't1'}],
                'events': [{'event_type': 'run_started'}, {'event_type': 'run_failed'}],
                'evals': [],
                'diagnosis': {'root_cause': 'tool_or_provider_failure', 'evidence': [{'event_type': 'run_failed'}]},
            },
            expected_statuses={'completed', 'waiting_approval'},
        )
    except RuntimeError as exc:
        assert 'unexpected status=failed' in str(exc)
    else:
        raise AssertionError('expected failed status to be rejected')


def test_review_query_string_includes_filters() -> None:
    common = _load('real_playbook_common', 'real_playbook_common.py')

    assert common.review_query_string(playbook_key='build-in-public', since_hours=24) == '?playbook_key=build-in-public&since_hours=24'


def test_acceptance_validator_accepts_healthy_waiting_user() -> None:
    common = _load('real_playbook_common', 'real_playbook_common.py')
    summary = common.validate_terminal_run(
        {
            'id': 'run-2',
            'status': 'waiting_user',
            'tasks': [{'id': 't1'}],
            'events': [{'event_type': 'run_started'}, {'event_type': 'l2_message_user'}],
            'evals': [],
            'diagnosis': {'root_cause': 'none', 'improvement_needed': False, 'evidence': []},
            'improvement_proposals': [],
        },
        expected_statuses=common.SUCCESSFUL_TERMINAL,
    )

    assert summary['status'] == 'waiting_user'


def test_goal_discovery_waiting_user_requires_structured_interaction() -> None:
    common = _load('real_playbook_common', 'real_playbook_common.py')
    summary = common.validate_terminal_run(
        {
            'id': 'run-3',
            'playbook_key': 'goal-discovery',
            'status': 'waiting_user',
            'output': {
                'message': 'Choose the path that matters first.',
                'interaction': {
                    'kind': 'goal_clarification',
                    'question': 'Which direction matters first?',
                    'options': [
                        {'id': 'ops', 'label': 'Ops', 'description': 'Launch readiness first.'},
                        {'id': 'product', 'label': 'Product', 'description': 'Goal discovery UX first.'},
                    ],
                },
            },
            'tasks': [{'id': 't1'}],
            'events': [{'event_type': 'run_started'}, {'event_type': 'l2_message_user'}],
            'evals': [],
            'diagnosis': {'root_cause': 'none', 'improvement_needed': False, 'evidence': []},
            'improvement_proposals': [],
        },
        expected_statuses=common.SUCCESSFUL_TERMINAL,
    )

    assert summary['status'] == 'waiting_user'
