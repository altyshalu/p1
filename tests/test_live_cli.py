from rich.console import Console

from l2l3_protocol.live.cli import load_sources_file
from l2l3_protocol.live.render import render_run_snapshot


def test_live_renderer_shows_pipeline_artifacts_evals_and_approval() -> None:
    run = {
        "id": "12345678-abcd",
        "status": "waiting_approval",
        "process_key": "build-in-public-trend-radar",
        "goal": "real trend radar run",
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


def test_live_renderer_toggles_full_event_payloads() -> None:
    long_url = f"https://example.com/{'x' * 220}"
    run = {
        "id": "12345678-abcd",
        "status": "running",
        "process_key": "build-in-public-trend-radar",
        "goal": "real trend radar run",
        "tasks": [],
        "artifacts": [],
        "evals": [],
        "events": [
            {
                "event_type": "l2_action_selected",
                "payload": {"trend_signals": [{"title": "Long signal", "url": long_url}]},
            }
        ],
    }

    compact_console = Console(record=True, width=120)
    compact_console.print(render_run_snapshot(run, show_full_events=False))
    compact_output = compact_console.export_text()

    full_console = Console(record=True, width=160)
    full_console.print(render_run_snapshot(run, show_full_events=True))
    full_output = full_console.export_text()

    assert "compact" in compact_output
    assert "..." in compact_output
    assert long_url not in compact_output
    assert "full" in full_output
    assert "Long signal" in full_output
    assert "..." not in full_output


def test_load_sources_file_requires_real_explicit_inputs(tmp_path) -> None:
    path = tmp_path / "sources.json"
    path.write_text(
        """
        {
          "sources": [
            {
              "source": "github",
              "items": [
                {
                  "title": "openai/codex",
                  "url": "https://github.com/openai/codex",
                  "summary": "Real repository source result"
                }
              ]
            }
          ]
        }
        """
    )

    assert load_sources_file(path) == [
        {
            "source": "github",
            "items": [
                {
                    "title": "openai/codex",
                    "url": "https://github.com/openai/codex",
                    "summary": "Real repository source result",
                }
            ],
        }
    ]


def test_load_sources_file_rejects_empty_sources(tmp_path) -> None:
    path = tmp_path / "sources.json"
    path.write_text('{"sources": []}')

    try:
        load_sources_file(path)
    except ValueError as exc:
        assert "non-empty sources list" in str(exc)
    else:
        raise AssertionError("empty sources must be rejected")
