from l2l3_protocol.services.telegram_control import (
    TelegramConfig,
    TelegramControlBot,
    default_p1_inputs,
    format_drafts,
    format_metrics,
    format_summary,
    is_allowed_chat,
    parse_command,
)


def test_telegram_parse_command_strips_bot_username() -> None:
    assert parse_command("/status@abrt_bot run-1") == ("/status", "run-1")


def test_telegram_default_p1_inputs_use_real_demo_target() -> None:
    inputs = default_p1_inputs()

    assert inputs["mode"] == "full_pipeline"
    assert inputs["limit"] == 20
    assert inputs["sources"] == ["exa", "apify_funding", "apify_crunchbase", "apify_linkedin"]
    assert inputs["allow_google_sheet_write"] is True
    assert inputs["allow_outreach_master_write"] is True
    assert "operator-angels" in inputs["query"]


def test_telegram_access_check_requires_allowed_chat_id() -> None:
    assert is_allowed_chat(833911206, {833911206}) is True
    assert is_allowed_chat(123, {833911206}) is False


def test_telegram_format_summary_metrics_and_drafts() -> None:
    summary = {
        "id": "run-1",
        "status": "waiting_approval",
        "playbook_key": "p1-operator-outreach",
        "goal": "prove p1",
        "pending_actions": [{"type": "approval"}],
        "latest_diagnosis": {"root_cause": "none"},
        "latest_metrics": {"raw_leads": 20, "gateway_approved": 3, "drafted": 3, "eval_passed": True},
    }
    run = {
        "output": {
            "approval_package": {
                "outreach_drafts": [
                    {
                        "name": "Arianna Simpson",
                        "current_role": "Angel investor",
                        "text": "ABRT/Limpid note grounded in real evidence.",
                    }
                ]
            }
        }
    }

    assert "waiting_approval" in format_summary(summary)
    assert "gateway_approved: 3" in format_metrics(summary)
    assert "Arianna Simpson" in format_drafts(run)


def test_telegram_bot_starts_real_p1_run_through_backend_client() -> None:
    class Api:
        def create_p1_run(self):
            return {"id": "run-1", "status": "created"}

    bot = TelegramControlBot(TelegramConfig(token="token", allowed_chat_ids={833911206}), api=Api(), telegram=None)

    assert "run-1" in bot.handle_text("/p1")
