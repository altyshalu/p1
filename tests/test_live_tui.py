import pytest
from rich.text import Text

from l2l3_protocol.live.tui import (
    LiveRunApp,
    _collect_drafts,
    _compact_payload,
    _draft_text,
    _drafts_markdown,
    _events_markdown,
    _prompt_markdown,
    _state_text,
    parse_approval_command,
)


class FakeLiveClient:
    async def get_run(self, run_id: str) -> dict:
        return {
            "id": run_id,
            "status": "waiting_user",
            "process_key": "build-in-public-trend-radar",
            "goal": "inspect live tui",
            "tasks": [{"status": "completed", "worker_profile": "collector", "task_type": "collect", "goal": "collect real data"}],
            "evals": [],
            "artifacts": [],
            "events": [{"event_type": "l2_message_user", "payload": {"message": "Give me themes."}}],
        }

    async def send_message(self, run_id: str, message: str) -> dict:
        return await self.get_run(run_id) | {"status": "running", "events": [{"event_type": "user_message", "payload": {"message": message}}]}


@pytest.mark.asyncio
async def test_live_app_mounts_and_focuses_waiting_user_input() -> None:
    app = LiveRunApp(api_url="http://localhost:8080", run_id="run-1")
    app.client = FakeLiveClient()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)

        assert app.query_one("#command").disabled is False
        assert app.query_one("#command").placeholder == "Answer L2 here and press Enter"


@pytest.mark.asyncio
async def test_live_app_opens_detail_windows() -> None:
    app = LiveRunApp(api_url="http://localhost:8080", run_id="run-1")
    app.client = FakeLiveClient()

    async with app.run_test(size=(120, 40)) as pilot:
        await pilot.pause(0.2)
        await pilot.press("f2")
        await pilot.pause(0.1)

        assert app.screen.__class__.__name__ == "DetailScreen"


def test_parse_approval_command_accepts_approve_aliases() -> None:
    command = parse_approval_command("yes")

    assert command.action == "approve"
    assert command.payload == {}


def test_parse_approval_command_reject_requires_reason() -> None:
    with pytest.raises(ValueError, match="reject <reason>"):
        parse_approval_command("reject")


def test_parse_approval_command_builds_reject_payload() -> None:
    command = parse_approval_command("reject: claims are not grounded")

    assert command.action == "reject"
    assert command.payload == {"reason": "claims are not grounded"}


def test_parse_approval_command_builds_edit_payload() -> None:
    command = parse_approval_command("edit make it sharper")

    assert command.action == "request_edit"
    assert command.payload == {"message": "make it sharper"}


def test_collect_drafts_prefers_real_artifacts() -> None:
    run = {
        "artifacts": [
            {"artifact_type": "channel_drafts", "payload": {"drafts": [{"channel": "x", "thread": ["one", "two"]}]}},
            {"artifact_type": "edited_drafts", "payload": {"edited_drafts": [{"channel": "x", "text": "edited"}]}},
        ]
    }

    drafts = _collect_drafts(run)

    assert [draft["channel"] for draft in drafts] == ["x", "x"]
    assert _draft_text(drafts[0]) == "one\n\ntwo"
    assert _draft_text(drafts[1]) == "edited"


def test_prompt_markdown_preserves_l2_formatting() -> None:
    run = {
        "status": "waiting_user",
        "events": [{"event_type": "l2_message_user", "payload": {"message": "**Judge failed**\n- claim ✅"}}],
        "output": {},
    }

    markdown = _prompt_markdown(run)

    assert "# L2 needs your answer" in markdown
    assert "**Judge failed**" in markdown
    assert "- claim ✅" in markdown


def test_detail_markdown_builders_include_full_content() -> None:
    run = {
        "artifacts": [{"payload": {"drafts": [{"channel": "x", "text": "full draft body"}]}}],
        "events": [{"event_type": "l2_action_selected", "payload": {"reason": "long reason"}}],
    }

    assert "full draft body" in _drafts_markdown(run)
    assert "l2_action_selected" in _events_markdown(run, show_full=True)
    assert "long reason" in _events_markdown(run, show_full=True)


def test_compact_payload_preserves_toggle_signal() -> None:
    payload = {"trend_signals": [{"url": f"https://example.com/{'x' * 500}"}]}

    assert _compact_payload(payload).endswith("...")


def test_state_text_returns_styled_text() -> None:
    state = _state_text("failed")

    assert isinstance(state, Text)
    assert state.plain == "fail"
