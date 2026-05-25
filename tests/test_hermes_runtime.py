import asyncio
import sys
import threading
import types

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.runtime.hermes import HermesRuntime


@pytest.mark.asyncio
async def test_hermes_runtime_runs_agent_conversation_off_event_loop_thread(monkeypatch: pytest.MonkeyPatch) -> None:
    event_loop_thread_id = threading.get_ident()
    worker_thread_ids: list[int] = []

    class FakeAIAgent:
        def __init__(self, **_: object) -> None:
            pass

        def run_conversation(self, **_: object) -> dict[str, str]:
            worker_thread_ids.append(threading.get_ident())
            return {"final_response": "ok"}

    monkeypatch.setitem(sys.modules, "run_agent", types.SimpleNamespace(AIAgent=FakeAIAgent))
    runtime = HermesRuntime(Settings(hermes_enabled=True, deepseek_api_key="test"))

    result = await runtime.run("prompt", "system", "task-id")

    assert result == "ok"
    assert worker_thread_ids
    assert worker_thread_ids[0] != event_loop_thread_id
