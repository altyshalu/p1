import importlib.util
from pathlib import Path


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
