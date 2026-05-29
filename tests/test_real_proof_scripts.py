import importlib.util
import io
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
    monkeypatch.setattr(sys, 'argv', ['real-p1-idempotency-proof.py', '--inputs-json', '/tmp/in.json'])

    try:
        module.main()
    except SystemExit as exc:
        assert 'no duplicate-skip evidence found' in str(exc)
    else:
        raise AssertionError('expected SystemExit')


def test_p1_readiness_reports_missing_required_keys(monkeypatch, tmp_path: Path) -> None:
    module = _load_module('real-p1-readiness.py', 'real_p1_readiness')
    env_path = tmp_path / 'test.env'
    env_path.write_text('GEMINI_API_KEY=test\n')
    monkeypatch.setattr(module, 'require_health', lambda _base_url: {'status': 'ok'})
    monkeypatch.setattr(module, 'require_capabilities', lambda _base_url: {'hermes': {'available': True}})
    monkeypatch.setattr(module, 'require_hub_seed', lambda _base_url, _sync_yaml: {'playbook_key': 'p1-operator-outreach'})

    report = module.readiness_report('http://api', str(env_path), 'source_only', {}, True)

    assert report['ready'] is False
    assert 'APIFY_API_TOKEN' in report['missing_required_keys']


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
    assert report['path_checks']['P1_DOSSIER_SOURCE_PATH'] is True


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


def test_p1_proof_pack_summarizes_internal_failure(monkeypatch) -> None:
    module = _load_module('real-p1-proof-pack.py', 'real_p1_proof_pack')
    monkeypatch.setattr(module, 'run_step', lambda name, command: {'name': name, 'status': 'pass', 'returncode': 0, 'command': command, 'stdout': '{}', 'stderr': ''} if name == 'readiness' else {'name': name, 'status': 'fail_internal', 'returncode': 1, 'command': command, 'stdout': '', 'stderr': 'boom'})
    monkeypatch.setattr(sys, 'argv', ['real-p1-proof-pack.py', '--skip-cache', '--skip-idempotency', '--full-inputs-json', '/tmp/in.json'])
    stdout = io.StringIO()
    monkeypatch.setattr(sys, 'stdout', stdout)

    exit_code = module.main()

    assert exit_code == 1
    assert 'fail_internal' in stdout.getvalue()
