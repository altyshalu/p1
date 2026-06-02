import importlib.util
import io
import json
import sys
from pathlib import Path


def _load_module(script_name: str, module_name: str):
    script_path = Path(__file__).resolve().parents[1] / "scripts" / script_name
    spec = importlib.util.spec_from_file_location(module_name, script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _load_real_before_after_proof_module():
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "real-before-after-proof.py"
    spec = importlib.util.spec_from_file_location("real_before_after_proof", script_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_before_after_proof_accepts_already_proven_proposal(monkeypatch) -> None:
    module = _load_real_before_after_proof_module()

    def fake_request_json(url: str, **kwargs):
        assert url == "http://api/improvement-proposals"
        return [
            {
                "id": "proposal-1",
                "status": "proven",
                "proof_spec": {"real_run_required": True},
            }
        ]

    monkeypatch.setattr(module, "request_json", fake_request_json)

    proposal = module.require_implemented_proposal("http://api", "proposal-1", "run-1")

    assert proposal["status"] == "proven"


def test_before_after_proof_rejects_new_after_run_root_cause(monkeypatch) -> None:
    module = _load_real_before_after_proof_module()
    mark_proven_called = False

    def fake_request_json(url: str, **kwargs):
        nonlocal mark_proven_called
        if url == "http://api/health":
            return {"status": "ok"}
        if url == "http://api/runs/baseline-run":
            return {
                "id": "baseline-run",
                "status": "failed",
                "playbook_key": "build-in-public-trend-radar",
                "l2_mode": "execution",
                "goal": "Baseline",
                "input": {"inputs": {"query": "agent runtime"}, "require_human_approval": True},
                "diagnosis": {"root_cause": "quality_gate_failed", "summary": "Old claim grounding failure."},
            }
        if url == "http://api/improvement-proposals":
            return [
                {
                    "id": "proposal-1",
                    "status": "proven",
                    "failure_signature": "eval_failed:claim-grounding-judge",
                    "proof_spec": {
                        "real_run_required": True,
                        "expected_absent_signature": "eval_failed:claim-grounding-judge",
                    },
                }
            ]
        if url == "http://api/runs":
            return {"id": "after-run"}
        if url == "http://api/improvement-proposals/proposal-1/mark-proven":
            mark_proven_called = True
            return {"status": "proven"}
        raise AssertionError(f"unexpected URL: {url}")

    monkeypatch.setattr(module, "request_json", fake_request_json)
    monkeypatch.setattr(
        module,
        "wait_for_diagnosis",
        lambda api_url, run_id, timeout_seconds: {
            "id": "after-run",
            "status": "waiting_approval",
            "diagnosis": {
                "root_cause": "quality_gate_failed",
                "summary": "New draft quality failure.",
            },
            "improvement_proposals": [
                {"failure_signature": "eval_failed:trend-draft-quality-judge"},
            ],
        },
    )

    try:
        module.run_before_after_proof("http://api", "baseline-run", "proposal-1", 1)
    except RuntimeError as exc:
        assert "after run ended with a new root cause" in str(exc)
    else:
        raise AssertionError("expected RuntimeError")
    assert mark_proven_called is False


def test_p1_real_common_assert_summary_shape_rejects_missing_fields() -> None:
    module = _load_module('p1_real_common.py', 'p1_real_common')

    try:
        module.assert_summary_shape({'status': 'completed'})
    except SystemExit as exc:
        assert 'missing required fields' in str(exc)
    else:
        raise AssertionError('expected SystemExit')


def test_p1_real_common_sends_operator_api_key(monkeypatch) -> None:
    module = _load_module('p1_real_common.py', 'p1_real_common')
    captured = {}

    class Response:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return None

        def read(self):
            return b'{"ok": true}'

    def fake_urlopen(request, timeout=120):
        captured['authorization'] = request.headers.get('Authorization') or request.headers.get('authorization')
        return Response()

    monkeypatch.setenv('L2L3_OPERATOR_API_KEY', 'secret')
    monkeypatch.setattr(module, 'urlopen', fake_urlopen)

    assert module.request_json('http://api/runs', method='POST', body={}) == {'ok': True}
    assert captured['authorization'] == 'Bearer secret'


def test_p1_full_proof_reports_waiting_approval_without_sheet_verification(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'existing_dossiers', 'require_human_approval': True})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs: {'id': 'run-1'})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'id': 'run-1', 'status': 'waiting_approval', 'diagnosis': None})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'status': 'waiting_approval', 'playbook_key': 'p1-operator-outreach', 'goal': 'proof', 'latest_metrics': {}, 'artifact_counts': {}, 'task_status_counts': {}, 'pending_actions': [{'type': 'approval'}], 'latest_approval_preview': {}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--inputs-json', '/tmp/in.json'])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 0
    assert 'waiting_approval' in stdout.getvalue()


def test_p1_full_proof_accepts_existing_run_id_without_creating_run(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    created = False
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'existing_dossiers'})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})

    def create_run_should_not_be_called(*_args, **_kwargs):
        nonlocal created
        created = True
        raise AssertionError('create_run should not be called for --existing-run-id')

    monkeypatch.setattr(module, 'create_run', create_run_should_not_be_called)
    monkeypatch.setattr(
        module,
        'request_json',
        lambda _url: {
            'id': 'run-existing',
            'status': 'completed',
            'playbook_key': 'p1-operator-outreach',
            'input': {'inputs': {'mode': 'existing_dossiers'}},
            'diagnosis': None,
        },
    )
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'status': 'completed', 'playbook_key': 'p1-operator-outreach', 'goal': 'proof', 'latest_metrics': {'drafted': 1}, 'artifact_counts': {}, 'task_status_counts': {}, 'pending_actions': [], 'latest_approval_preview': {}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--inputs-json', '/tmp/in.json', '--existing-run-id', 'run-existing'])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 0
    assert created is False
    assert '"run_id": "run-existing"' in stdout.getvalue()


def test_p1_full_proof_rejects_existing_run_input_mismatch(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'full_pipeline'})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(
        module,
        'request_json',
        lambda _url: {
            'id': 'run-existing',
            'status': 'completed',
            'playbook_key': 'p1-operator-outreach',
            'input': {'inputs': {'mode': 'existing_dossiers'}},
            'diagnosis': None,
        },
    )
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--inputs-json', '/tmp/in.json', '--existing-run-id', 'run-existing'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'existing run inputs do not match --inputs-json' in str(exc)
    else:
        raise AssertionError('expected mismatched existing-run proof to fail')


def test_p1_full_proof_rejects_existing_run_wrong_playbook(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(
        module,
        'request_json',
        lambda _url: {
            'id': 'run-existing',
            'status': 'completed',
            'playbook_key': 'build-in-public-trend-radar',
            'input': {'inputs': {'query': 'agent memory'}},
            'diagnosis': None,
        },
    )
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--existing-run-id', 'run-existing'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'not a P1 operator outreach run' in str(exc)
    else:
        raise AssertionError('expected wrong playbook proof reuse to fail')


def test_p1_full_proof_requires_write_verification_from_existing_run_inputs(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(
        module,
        'request_json',
        lambda _url: {
            'id': 'run-existing',
            'status': 'completed',
            'playbook_key': 'p1-operator-outreach',
            'input': {'inputs': {'mode': 'existing_dossiers', 'allow_google_sheet_write': True}},
            'diagnosis': None,
        },
    )
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'status': 'completed', 'playbook_key': 'p1-operator-outreach', 'goal': 'proof', 'latest_metrics': {'drafted': 1}, 'artifact_counts': {}, 'task_status_counts': {}, 'pending_actions': [], 'latest_approval_preview': {}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--existing-run-id', 'run-existing'])

    try:
        module.main()
    except SystemExit as exc:
        assert '--verify-sheet' in str(exc)
    else:
        raise AssertionError('expected existing write-enabled run without physical verification to fail')


def test_p1_full_proof_rejects_waiting_approval_when_external_writes_requested(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'existing_dossiers', 'allow_google_sheet_write': True})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs: {'id': 'run-1'})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'id': 'run-1', 'status': 'waiting_approval', 'diagnosis': None})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'status': 'waiting_approval', 'playbook_key': 'p1-operator-outreach', 'goal': 'proof', 'latest_metrics': {}, 'artifact_counts': {}, 'task_status_counts': {}, 'pending_actions': [{'type': 'approval'}], 'latest_approval_preview': {}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--inputs-json', '/tmp/in.json'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'external writes were requested but run is still waiting_approval' in str(exc)
    else:
        raise AssertionError('expected incomplete external-write proof to fail')


def test_p1_full_proof_requires_physical_verification_flags_for_completed_writes(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'existing_dossiers', 'allow_google_sheet_write': True, 'allow_data_lake_write': True})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs: {'id': 'run-1'})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'id': 'run-1', 'status': 'completed', 'diagnosis': None})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'status': 'completed', 'playbook_key': 'p1-operator-outreach', 'goal': 'proof', 'latest_metrics': {'drafted': 1}, 'artifact_counts': {}, 'task_status_counts': {}, 'pending_actions': [], 'latest_approval_preview': {}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--inputs-json', '/tmp/in.json'])

    try:
        module.main()
    except SystemExit as exc:
        message = str(exc)
        assert '--verify-sheet' in message
        assert '--verify-data-lake' in message
    else:
        raise AssertionError('expected completed external-write proof without verification flags to fail')


def test_p1_full_proof_verify_outreach_master(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    master_path = tmp_path / 'master.json'
    master_path.write_text(json.dumps({'drafts': [{'run_id': 'run-1', 'lead_id': 'lead-1'}]}), encoding='utf-8')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'existing_dossiers'})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs: {'id': 'run-1'})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'id': 'run-1', 'status': 'completed', 'diagnosis': None})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {
        'status': 'completed',
        'playbook_key': 'p1-operator-outreach',
        'goal': 'proof',
        'latest_metrics': {'drafted': 1},
        'artifact_counts': {},
        'task_status_counts': {},
        'pending_actions': [],
        'latest_approval_preview': {'outreach_master': {'path': str(master_path), 'entries': [{'run_id': 'run-1', 'lead_id': 'lead-1'}]}},
    })
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--inputs-json', '/tmp/in.json', '--verify-outreach-master'])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 0
    assert 'outreach_master_verification' in stdout.getvalue()


def test_p1_full_proof_verify_data_lake(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    lake = tmp_path / 'lake'
    lake.mkdir()
    (lake / 'lead-1.json').write_text('{}', encoding='utf-8')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'existing_dossiers'})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs: {'id': 'run-1'})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'id': 'run-1', 'status': 'completed', 'diagnosis': None})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {
        'status': 'completed',
        'playbook_key': 'p1-operator-outreach',
        'goal': 'proof',
        'latest_metrics': {'written_count': 1},
        'artifact_counts': {},
        'task_status_counts': {},
        'pending_actions': [],
        'latest_approval_preview': {'data_lake': {'path': str(lake), 'files': [{'lead_id': 'lead-1'}]}},
    })
    monkeypatch.setattr(sys, 'argv', ['real-p1-full-proof.py', '--inputs-json', '/tmp/in.json', '--verify-data-lake'])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 0
    assert 'data_lake_verification' in stdout.getvalue()


def test_p1_full_proof_verify_quality_accepts_golden_icp_run() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Product Angel'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'PASS',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            },
                        }
                    ]
                },
            },
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {
                            'name': 'Product Angel',
                            'linkedin_url': 'https://www.linkedin.com/in/productangel',
                            'identity_status': 'verified_linkedin',
                            'text': 'ABRT/Limpid is mapping product-led angels. Would a quick 30-minute call next week make sense?',
                            'status': 'draft',
                            'publish': False,
                            'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            'claims': [{'text': 'Product angel.', 'source_url': 'https://www.linkedin.com/in/productangel'}],
                        }
                    ]
                },
            },
        ]
    }

    assert module.verify_p1_quality(run) == {'gateway_approved': 1, 'drafts_verified': 1}


def test_p1_full_proof_verify_quality_rejects_duplicate_meeting_cta() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Product Angel'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'PASS',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            },
                        }
                    ]
                },
            },
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {
                            'name': 'Product Angel',
                            'linkedin_url': 'https://www.linkedin.com/in/productangel',
                            'identity_status': 'verified_linkedin',
                            'text': (
                                'ABRT/Limpid is mapping product-led angels. '
                                'I would love to connect for 30 minutes next week. '
                                'Would a quick 30-minute call next week make sense?'
                            ),
                            'status': 'draft',
                            'publish': False,
                            'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            'claims': [{'text': 'Product angel.', 'source_url': 'https://www.linkedin.com/in/productangel'}],
                        }
                    ]
                },
            },
        ]
    }

    try:
        module.verify_p1_quality(run)
    except SystemExit as exc:
        assert 'duplicate_meeting_cta' in str(exc)
    else:
        raise AssertionError('expected duplicate meeting CTA to fail P1 quality verification')


def test_p1_full_proof_verify_quality_rejects_same_sentence_duplicate_meeting_cta() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Product Angel'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'PASS',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            },
                        }
                    ]
                },
            },
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {
                            'name': 'Product Angel',
                            'linkedin_url': 'https://www.linkedin.com/in/productangel',
                            'identity_status': 'verified_linkedin',
                            'text': 'ABRT/Limpid is mapping product-led angels. Would a quick 30-minute call next week or a brief chat next week make sense?',
                            'status': 'draft',
                            'publish': False,
                            'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            'claims': [{'text': 'Product angel.', 'source_url': 'https://www.linkedin.com/in/productangel'}],
                        }
                    ]
                },
            },
        ]
    }

    try:
        module.verify_p1_quality(run)
    except SystemExit as exc:
        assert 'duplicate_meeting_cta' in str(exc)
    else:
        raise AssertionError('expected same-sentence duplicate meeting CTA to fail P1 quality verification')


def test_p1_full_proof_verify_quality_rejects_resonates_only_without_meeting_cta() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Product Angel'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'PASS',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            },
                        }
                    ]
                },
            },
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {
                            'name': 'Product Angel',
                            'linkedin_url': 'https://www.linkedin.com/in/productangel',
                            'identity_status': 'verified_linkedin',
                            'text': 'ABRT/Limpid is mapping product-led angels. Curious whether that thesis resonates.',
                            'status': 'draft',
                            'publish': False,
                            'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            'claims': [{'text': 'Product angel.', 'source_url': 'https://www.linkedin.com/in/productangel'}],
                        }
                    ]
                },
            },
        ]
    }

    try:
        module.verify_p1_quality(run)
    except SystemExit as exc:
        assert 'missing_clear_cta' in str(exc)
    else:
        raise AssertionError('expected resonates-only draft to fail P1 quality verification')


def test_p1_full_proof_verify_quality_rejects_unverified_linkedin_identity() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Needs Review'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'PASS',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.crunchbase.com/person/example'],
                            },
                        }
                    ]
                },
            },
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {
                            'name': 'Needs Review',
                            'linkedin_url': '',
                            'identity_status': 'needs_review',
                            'text': 'ABRT/Limpid draft',
                            'status': 'draft',
                            'publish': False,
                            'evidence_urls': ['https://www.crunchbase.com/person/example'],
                            'claims': [{'text': 'Needs Review is an investor.', 'source_url': 'https://www.crunchbase.com/person/example'}],
                        }
                    ]
                },
            },
        ]
    }

    try:
        module.verify_p1_quality(run)
    except SystemExit as exc:
        assert 'missing_verified_person_linkedin' in str(exc)
        assert 'identity_status_not_verified' in str(exc)
    else:
        raise AssertionError('expected unverified LinkedIn identity to fail P1 quality verification')


def test_p1_full_proof_verify_quality_rejects_linkedin_without_matching_evidence() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Product Angel'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'PASS',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            },
                        }
                    ]
                },
            },
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {
                            'name': 'Product Angel',
                            'linkedin_url': 'https://www.linkedin.com/in/productangel',
                            'identity_status': 'verified_linkedin',
                            'text': 'ABRT/Limpid is mapping product-led angels. Would a quick 30-minute call next week make sense?',
                            'status': 'draft',
                            'publish': False,
                            'evidence_urls': ['https://www.crunchbase.com/person/productangel'],
                            'claims': [{'text': 'Product angel.', 'source_url': 'https://www.crunchbase.com/person/productangel'}],
                        }
                    ]
                },
            },
        ]
    }

    try:
        module.verify_p1_quality(run)
    except SystemExit as exc:
        assert 'linkedin_not_evidence_backed' in str(exc)
    else:
        raise AssertionError('expected unbacked LinkedIn URL to fail P1 quality verification')


def test_p1_full_proof_verify_quality_rejects_dead_live_linkedin_profile(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setattr(module, 'linkedin_profile_url_is_live', lambda _url: False)
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Product Angel'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'PASS',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            },
                        }
                    ]
                },
            },
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {
                            'name': 'Product Angel',
                            'linkedin_url': 'https://www.linkedin.com/in/productangel',
                            'identity_status': 'verified_linkedin',
                            'text': 'ABRT/Limpid is mapping product-led angels. Would a quick 30-minute call next week make sense?',
                            'status': 'draft',
                            'publish': False,
                            'evidence_urls': ['https://www.linkedin.com/in/productangel'],
                            'claims': [{'text': 'Product angel.', 'source_url': 'https://www.linkedin.com/in/productangel'}],
                        }
                    ]
                },
            },
        ]
    }

    try:
        module.verify_p1_quality(run, verify_linkedin_live=True)
    except SystemExit as exc:
        assert 'linkedin_profile_not_live' in str(exc)
    else:
        raise AssertionError('expected dead live LinkedIn URL to fail P1 quality verification')


def test_p1_full_proof_verify_quality_rejects_missing_investor_fit() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_gateway_evaluations',
                'payload': {
                    'gateway_evaluations': [
                        {
                            'dossier': {'identity': {'name': 'Operator Only'}},
                            'gateway': {
                                'decision': 'awaiting_outreach',
                                'identity_confidence': 96,
                                'product_b2c_fit': 'PASS',
                                'product_leadership_fit': 'PASS',
                                'verified_investor_fit': 'FAIL',
                                'bandwidth_signal': 'HIGH',
                                'liquidity_signal': 'YES',
                                'exclusion_signal': 'NO',
                                'evidence_urls': ['https://www.linkedin.com/in/operator'],
                            },
                        }
                    ]
                },
            }
        ]
    }

    try:
        module.verify_p1_quality(run)
    except SystemExit as exc:
        assert 'verified_investor_fit_not_pass' in str(exc)
    else:
        raise AssertionError('expected SystemExit')


def test_p1_cache_proof_rejects_missing_cache_hits(monkeypatch) -> None:
    module = _load_module('real-p1-cache-proof.py', 'real_p1_cache_proof')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'source_only'})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs, require_human_approval=False: {'id': _goal})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'status': 'completed'})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'latest_metrics': {'provider_cache_hits': 0}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-cache-proof.py', '--inputs-json', '/tmp/in.json'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'no provider_cache_hits' in str(exc)
    else:
        raise AssertionError('expected SystemExit')


def test_p1_cache_proof_rejects_missing_triage_cache_hits_when_requested(monkeypatch) -> None:
    module = _load_module('real-p1-cache-proof.py', 'real_p1_cache_proof')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'source_only', 'use_triage_cache': True})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs, require_human_approval=False: {'id': _goal})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'status': 'completed'})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'latest_metrics': {'provider_cache_hits': 1, 'triage_cache_hits': 0}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-cache-proof.py', '--inputs-json', '/tmp/in.json'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'no triage_cache_hits' in str(exc)
    else:
        raise AssertionError('expected missing triage cache hits to fail')


def test_p1_cache_proof_rejects_missing_triage_cache_hits_when_enabled_by_env(monkeypatch) -> None:
    module = _load_module('real-p1-cache-proof.py', 'real_p1_cache_proof')
    monkeypatch.setenv('P1_USE_TRIAGE_CACHE', 'true')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'source_only'})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs, require_human_approval=False: {'id': _goal})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'status': 'completed'})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'latest_metrics': {'provider_cache_hits': 1, 'triage_cache_hits': 0}})
    monkeypatch.setattr(sys, 'argv', ['real-p1-cache-proof.py', '--inputs-json', '/tmp/in.json'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'no triage_cache_hits' in str(exc)
    else:
        raise AssertionError('expected env-enabled missing triage cache hits to fail')


def test_p1_idempotency_proof_rejects_missing_duplicate_skip_evidence(monkeypatch) -> None:
    module = _load_module('real-p1-idempotency-proof.py', 'real_p1_idempotency_proof')
    monkeypatch.setattr(module, 'load_inputs', lambda _path: {'mode': 'existing_dossiers'})
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'create_run', lambda _base_url, _goal, _inputs, require_human_approval=True: {'id': 'run-1'})
    states = iter([{'status': 'waiting_approval'}, {'status': 'completed', 'events': []}, {'status': 'completed', 'events': []}])
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: next(states))
    monkeypatch.setattr(module, 'approve_run', lambda _base_url, _run_id: {'status': 'completed'})
    monkeypatch.setattr(module, 'get_summary', lambda _base_url, _run_id: {'latest_metrics': {'sheet_duplicate_skipped': 0, 'outreach_master_duplicate_skipped': 0}})
    monkeypatch.setattr(module, 'find_duplicate_events', lambda _run: {'p1_external_sync_duplicate_skipped': 0, 'p1_outreach_master_duplicate_skipped': 0, 'p1_data_lake_duplicate_skipped': 0})
    monkeypatch.setattr(module, 'duplicate_sync_check', lambda _run: (_ for _ in ()).throw(SystemExit('idempotency proof failed: duplicate sync did not skip every draft')))
    monkeypatch.setattr(sys, 'argv', ['real-p1-idempotency-proof.py', '--inputs-json', '/tmp/in.json'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'duplicate sync did not skip every draft' in str(exc)
    else:
        raise AssertionError('expected SystemExit')


def test_p1_idempotency_proof_accepts_existing_completed_run(monkeypatch) -> None:
    module = _load_module('real-p1-idempotency-proof.py', 'real_p1_idempotency_proof')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'request_json', lambda _url: {'status': 'completed'})
    monkeypatch.setattr(module, 'approve_run', lambda _base_url, _run_id: {'status': 'completed'})
    monkeypatch.setattr(module, 'wait_for_run', lambda _base_url, _run_id, _timeout: {'status': 'completed', 'events': []})
    monkeypatch.setattr(
        module,
        'get_summary',
        lambda _base_url, _run_id: {'latest_metrics': {'sheet_written': 3, 'outreach_master_written': 3, 'data_lake_written': 5}},
    )
    monkeypatch.setattr(module, 'find_duplicate_events', lambda _run: {'p1_external_sync_duplicate_skipped': 0})
    monkeypatch.setattr(module, 'duplicate_sync_check', lambda _run: {'expected_drafts': 3, 'sheet_duplicate_skipped': 3, 'outreach_master_duplicate_skipped': 3})
    monkeypatch.setattr(sys, 'argv', ['real-p1-idempotency-proof.py', '--run-id', 'run-1'])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 0
    assert 'duplicate_worker_check' in stdout.getvalue()


def test_p1_readiness_reports_missing_required_keys(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-readiness.py', 'real_p1_readiness')
    env_path = tmp_path / 'test.env'
    env_path.write_text('GEMINI_API_KEY=test\n')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'require_hub_seed', lambda _base_url, _sync_yaml: {'playbook_key': 'p1-operator-outreach'})

    report = module.readiness_report('http://api', str(env_path), 'source_only', {'sources': ['exa']}, True)

    assert report['ready'] is False
    assert 'EXA_API_KEY' in report['missing_required_keys']


def test_p1_readiness_requires_apify_and_exa_for_funding_source(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-readiness.py', 'real_p1_readiness')
    env_path = tmp_path / 'test.env'
    env_path.write_text('GEMINI_API_KEY=test\n')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'require_hub_seed', lambda _base_url, _sync_yaml: {'playbook_key': 'p1-operator-outreach'})

    report = module.readiness_report('http://api', str(env_path), 'source_only', {'sources': ['apify_funding']}, True)

    assert report['ready'] is False
    assert report['missing_required_keys'] == ['APIFY_API_TOKEN', 'EXA_API_KEY']


def test_p1_readiness_reports_missing_runtime_inputs(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-readiness.py', 'real_p1_readiness')
    env_path = tmp_path / 'test.env'
    env_path.write_text('GEMINI_API_KEY=test\nEXA_API_KEY=test\nAPIFY_API_TOKEN=test\n')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'require_hub_seed', lambda _base_url, _sync_yaml: {'playbook_key': 'p1-operator-outreach'})

    report = module.readiness_report('http://api', str(env_path), 'source_only', {}, True, explicit_inputs_supplied=True)

    assert report['ready'] is False
    assert report['missing_runtime_inputs'] == ['mode', 'sources']


def test_p1_readiness_reports_ready_when_required_keys_exist(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-readiness.py', 'real_p1_readiness')
    env_path = tmp_path / 'test.env'
    dossier_dir = tmp_path / 'dossiers'
    dossier_dir.mkdir()
    env_path.write_text(f'GEMINI_API_KEY=test\nEXA_API_KEY=test\nP1_DOSSIER_SOURCE_PATH={dossier_dir}\n')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'require_hub_seed', lambda _base_url, _sync_yaml: {'playbook_key': 'p1-operator-outreach'})

    report = module.readiness_report('http://api', str(env_path), 'existing_dossiers', {}, True)

    assert report['ready'] is True
    assert report['missing_required_keys'] == []
    assert report['missing_runtime_inputs'] == []
    assert report['path_checks']['dossier_source_path'] is True


def test_p1_readiness_data_lake_write_does_not_accept_source_path(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-readiness.py', 'real_p1_readiness')
    source_dir = tmp_path / 'source-dossiers'
    source_dir.mkdir()
    env_path = tmp_path / 'test.env'
    env_path.write_text(
        f'GEMINI_API_KEY=test\nEXA_API_KEY=test\nAPIFY_API_TOKEN=test\nP1_DOSSIER_SOURCE_PATH={source_dir}\n',
        encoding='utf-8',
    )
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'require_hub_seed', lambda _base_url, _sync_yaml: {'playbook_key': 'p1-operator-outreach'})

    report = module.readiness_report(
        'http://api',
        str(env_path),
        'full_pipeline',
        {'mode': 'full_pipeline', 'sources': ['exa'], 'allow_data_lake_write': True},
        True,
        explicit_inputs_supplied=True,
    )

    assert report['ready'] is False
    assert report['missing_runtime_inputs'] == ['data_lake_dossier_path or dossier_output_path or P1_DOSSIER_OUTPUT_PATH']


def test_p1_readiness_main_returns_nonzero_when_not_ready(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-readiness.py', 'real_p1_readiness')
    env_path = tmp_path / 'test.env'
    env_path.write_text('GEMINI_API_KEY=test\n')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'require_hub_seed', lambda _base_url, _sync_yaml: {'playbook_key': 'p1-operator-outreach'})
    monkeypatch.setattr(sys, 'argv', ['real-p1-readiness.py', '--base-url', 'http://api', '--env-file', str(env_path), '--mode', 'source_only'])

    assert module.main() == 1


def test_p1_proof_pack_classifies_missing_credentials_as_external_config() -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')

    assert module.classify_failure('missing required environment variable: APIFY_API_TOKEN') == 'fail_external_config'


def test_p1_proof_pack_classifies_timeout_as_external_dependency() -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')

    assert module.classify_failure('HTTP 429 provider timeout') == 'fail_external_dependency'


def test_p1_proof_pack_uses_scenario_mode_from_inputs(tmp_path: Path) -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')
    path = tmp_path / 'inputs.json'
    path.write_text('{"mode": "source_only"}')

    assert module.scenario_mode(str(path), 'full_pipeline') == 'source_only'


def test_p1_proof_pack_collects_action_items_from_preflights() -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')
    steps = [
        {
            'name': 'full_preflight',
            'status': 'fail_external_config',
            'json': {
                'missing_required_keys': ['APIFY_API_TOKEN'],
                'missing_runtime_inputs': ['mode', 'sources'],
                'path_checks': {'dossier_source_path': False},
            },
        },
        {'name': 'cache_preflight', 'status': 'skipped', 'reason': 'cache_inputs_json not provided'},
    ]

    items = module.collect_action_items(steps)

    assert 'Set required env key: APIFY_API_TOKEN' in items
    assert 'Provide required runtime input: mode' in items
    assert 'Provide required runtime input: sources' in items
    assert 'Create, mount, or fix required path: dossier_source_path' in items
    assert 'Provide --cache-inputs-json for cache proof execution' in items


def test_p1_proof_pack_skips_downstream_steps_when_scenario_preflight_fails(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')
    full_inputs = tmp_path / 'full.json'
    full_inputs.write_text('{"mode": "full_pipeline"}')

    def fake_run_step(name, command):
        if name == 'readiness':
            return {'name': 'readiness', 'status': 'pass', 'returncode': 0, 'command': command, 'stdout': '{}', 'stderr': ''}
        if name == 'full_preflight':
            return {'name': 'full_preflight', 'status': 'fail_external_config', 'returncode': 1, 'command': command, 'stdout': '{}', 'stderr': '', 'json': {'missing_required_keys': ['APIFY_API_TOKEN'], 'missing_runtime_inputs': ['sources']}}
        raise AssertionError(f'unexpected run_step call: {name}')

    monkeypatch.setattr(module, 'run_step', fake_run_step)
    monkeypatch.setattr(sys, 'argv', ['real-p1-proof-pack.py', '--full-inputs-json', str(full_inputs), '--skip-cache', '--skip-idempotency'])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 1
    rendered = stdout.getvalue()
    assert 'scenario preflight failed' in rendered
    assert 'Provide required runtime input: sources' in rendered




def test_p1_proof_pack_passes_verify_flags_to_full_proof(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')
    full_inputs = tmp_path / 'full.json'
    full_inputs.write_text('{"mode": "full_pipeline", "sources": ["exa"]}')
    captured = {}

    def fake_run_step(name, command):
        if name in {'readiness', 'full_preflight'}:
            return {'name': name, 'status': 'pass', 'returncode': 0, 'command': command, 'stdout': '{}', 'stderr': ''}
        if name == 'full_proof':
            captured['command'] = command
            return {'name': name, 'status': 'pass', 'returncode': 0, 'command': command, 'stdout': '{}', 'stderr': ''}
        return {'name': name, 'status': 'skipped', 'reason': 'disabled'}

    monkeypatch.setattr(module, 'run_step', fake_run_step)
    monkeypatch.setattr(
        sys,
        'argv',
        [
            'real-p1-proof-pack.py',
            '--full-inputs-json', str(full_inputs),
            '--skip-cache',
            '--skip-idempotency',
            '--approve',
            '--verify-sheet',
            '--verify-outreach-master',
            '--verify-data-lake',
            '--google-service-account-path', '/tmp/service-account.json',
        ],
    )

    exit_code = module.main()

    assert exit_code == 0
    command = captured['command']
    assert '--approve' in command
    assert '--env-file' in command
    assert '.env' in command
    assert '--verify-sheet' in command
    assert '--verify-outreach-master' in command
    assert '--verify-data-lake' in command
    assert '/tmp/service-account.json' in command


def test_full_proof_sheet_verification_uses_runtime_env(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setenv('P1_GOOGLE_SHEET_ID', 'sheet-from-env')
    monkeypatch.setenv('GOOGLE_SA_PATH', '/secure/service-account.json')

    config = module.sheet_verification_config({'google_sheets': {'tab_name': 'P1_L2L3_NEW_LEADS'}}, {}, None)

    assert config == {
        'spreadsheet_id': 'sheet-from-env',
        'tab_name': 'P1_L2L3_NEW_LEADS',
        'service_account_path': '/secure/service-account.json',
    }


def test_full_proof_loads_env_file_for_verification(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    env_path = tmp_path / '.env'
    env_path.write_text('P1_GOOGLE_SHEET_ID=sheet-from-file\nGOOGLE_SA_PATH=/secure/from-file.json\n', encoding='utf-8')
    monkeypatch.delenv('P1_GOOGLE_SHEET_ID', raising=False)
    monkeypatch.delenv('GOOGLE_SA_PATH', raising=False)

    module.load_env_file(str(env_path))
    config = module.sheet_verification_config({'google_sheets': {'tab_name': 'P1_L2L3_NEW_LEADS'}}, {}, None)

    assert config['spreadsheet_id'] == 'sheet-from-file'
    assert config['service_account_path'] == '/secure/from-file.json'


def test_full_proof_internal_paths_use_runtime_env(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.setenv('P1_OUTREACH_MASTER_PATH', '/ops/Outreach_Drafts_Master.json')
    monkeypatch.setenv('P1_DOSSIER_OUTPUT_PATH', '/data/dossiers')
    monkeypatch.setenv('P1_DOSSIER_SOURCE_PATH', '/source/dossiers')

    assert module.outreach_master_path({'outreach_master': {}}, {}) == '/ops/Outreach_Drafts_Master.json'
    assert module.data_lake_path({'data_lake': {}}, {}) == '/data/dossiers'


def test_full_proof_data_lake_path_does_not_fall_back_to_source(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    monkeypatch.delenv('P1_DOSSIER_OUTPUT_PATH', raising=False)
    monkeypatch.setenv('P1_DOSSIER_SOURCE_PATH', '/source/dossiers')

    assert module.data_lake_path({'data_lake': {}}, {}) == ''


def test_full_proof_sheet_verification_requires_run_lead_pairs(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')

    monkeypatch.setattr('l2l3_protocol.workers.p1_operator_worker._google_access_token', lambda _path: 'token')
    monkeypatch.setattr(
        'l2l3_protocol.workers.p1_operator_worker._request_json',
        lambda _url, token=None: {'values': [['run_id', 'lead_id'], ['run-1', 'lead-1']]},
    )

    result = module.verify_sheet_rows('sheet-id', 'P1_L2L3_NEW_LEADS', '/sa.json', [('run-1', 'lead-1')])

    assert result['matched_pairs'] == 1


def test_full_proof_sheet_verification_rejects_old_run_rows(monkeypatch) -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')

    monkeypatch.setattr('l2l3_protocol.workers.p1_operator_worker._google_access_token', lambda _path: 'token')
    monkeypatch.setattr(
        'l2l3_protocol.workers.p1_operator_worker._request_json',
        lambda _url, token=None: {'values': [['run_id', 'lead_id'], ['old-run', 'lead-1']]},
    )

    try:
        module.verify_sheet_rows('sheet-id', 'P1_L2L3_NEW_LEADS', '/sa.json', [('run-1', 'lead-1')])
    except SystemExit as exc:
        assert 'expected run_id/lead_id pairs are missing' in str(exc)
    else:
        raise AssertionError('expected sheet verification to reject old run row')


def test_full_proof_expected_ids_come_from_run_artifacts() -> None:
    module = _load_module('real-p1-full-proof.py', 'real_p1_full_proof')
    run = {
        'artifacts': [
            {
                'artifact_type': 'p1_outreach_drafts',
                'payload': {
                    'outreach_drafts': [
                        {'run_id': 'run-1', 'lead_id': 'lead-1'},
                        {'run_id': 'run-1', 'lead_id': 'lead-2'},
                    ]
                },
            },
            {
                'artifact_type': 'p1_dossiers',
                'payload': {
                    'p1_dossiers': [
                        {'identity': {'lead_id': 'lead-1'}},
                        {'identity': {'lead_id': 'lead-2'}},
                    ]
                },
            },
        ]
    }

    assert module.expected_draft_lead_ids(run) == ['lead-1', 'lead-2']
    assert module.expected_draft_pairs(run) == [('run-1', 'lead-1'), ('run-1', 'lead-2')]
    assert module.expected_dossier_lead_ids(run) == ['lead-1', 'lead-2']


def test_p1_idempotency_extracts_latest_outreach_drafts() -> None:
    module = _load_module('real-p1-idempotency-proof.py', 'real_p1_idempotency_proof')
    run = {
        'artifacts': [
            {'artifact_type': 'p1_outreach_drafts', 'payload': {'outreach_drafts': [{'run_id': 'run-1', 'lead_id': 'lead-1'}]}},
        ]
    }

    assert module.latest_outreach_drafts(run) == [{'run_id': 'run-1', 'lead_id': 'lead-1'}]


def test_p1_idempotency_duplicate_skip_evidence_requires_skip_count() -> None:
    module = _load_module('real-p1-idempotency-proof.py', 'real_p1_idempotency_proof')

    assert module.has_duplicate_skip_evidence({'sheet_duplicate_skipped': 1}, {'p1_external_sync_duplicate_skipped': 0}) is True
    assert module.has_duplicate_skip_evidence({}, {'p1_external_sync_duplicate_skipped': 0}) is False


def test_p1_proof_pack_summarizes_internal_failure(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')
    full_inputs = tmp_path / 'full.json'
    full_inputs.write_text('{"mode": "full_pipeline", "sources": ["exa"]}')

    def fake_run_step(name, command):
        if name in {'readiness', 'full_preflight'}:
            return {'name': name, 'status': 'pass', 'returncode': 0, 'command': command, 'stdout': '{}', 'stderr': ''}
        return {'name': name, 'status': 'fail_internal', 'returncode': 1, 'command': command, 'stdout': '', 'stderr': 'boom'}

    monkeypatch.setattr(module, 'run_step', fake_run_step)
    monkeypatch.setattr(sys, 'argv', ['real-p1-proof-pack.py', '--skip-cache', '--skip-idempotency', '--full-inputs-json', str(full_inputs)])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 1
    assert 'fail_internal' in stdout.getvalue()
    assert 'Fix backend/runtime failure in step full_proof' in stdout.getvalue()
