from l2l3_protocol.config import Settings
from l2l3_protocol.logging import configure_logging, get_logger


def test_settings_keep_external_memory_enabled_by_default() -> None:
    settings = Settings(_env_file=None)

    assert settings.agentmemory_enabled is True
    assert settings.mem0_enabled is True
    assert settings.hermes_enabled is True


def test_structured_logging_writes_jsonl_files(tmp_path) -> None:
    configure_logging(tmp_path, "INFO")
    get_logger("protocol.events").info("test_event", run_id="run-1", status="ok")

    assert (tmp_path / "app.jsonl").exists()
    assert (tmp_path / "protocol-events.jsonl").exists()
