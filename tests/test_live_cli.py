from rich.console import Console

from l2l3_protocol.live.render import render_run_snapshot


def test_live_renderer_shows_pipeline_artifacts_evals_and_approval() -> None:
    run = {
        "id": "12345678-abcd",
        "status": "waiting_approval",
        "process_key": "build-in-public-trend-radar",
        "goal": "demo",
        "tasks": [
            {"worker_profile": "trend-source-collector", "task_type": "collect", "status": "completed", "goal": "collect"},
            {"worker_profile": "trend-draft-quality-judge", "task_type": "judge", "status": "completed", "goal": "judge"},
            {"worker_profile": "approval-adapter", "task_type": "approve", "status": "completed", "goal": "approval"},
        ],
        "artifacts": [
            {"artifact_type": "channel_drafts", "payload": {"edited_drafts": [{"channel": "x", "text": "Draft text", "status": "draft"}]}},
        ],
        "evals": [
            {"eval_key": "trend-draft-quality", "passed": True, "score": 1.0, "threshold": 0.8},
        ],
        "events": [{"event_type": "process_started", "payload": {}}],
    }
    console = Console(record=True, width=120)

    console.print(render_run_snapshot(run))
    output = console.export_text()

    assert "build-in-public-trend-radar" in output
    assert "trend-source-collector" in output
    assert "trend-draft-quality" in output
    assert "Draft text" in output
    assert "waiting_approval" in output
