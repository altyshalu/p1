from pathlib import Path

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import TaskContract
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.l2_supervisor import L2Supervisor
from l2l3_protocol.runtime.l3_executor import L3SandboxExecutor, L3WorkerExecutionError


def process_pack() -> dict:
    return {
        "key": "build-in-public",
        "allowed_workers": ["signal-collector", "narrative-synthesizer"],
        "max_tasks_per_turn": 1,
    }


def worker_profiles() -> dict:
    return {
        "signal-collector": {"worker_type": "sandboxed_subprocess", "output_schema": {"required": ["signals"]}},
        "narrative-synthesizer": {"worker_type": "hermes_agent", "output_schema": {"required": ["content_atoms"]}},
    }


class FakeHermes(HermesRuntime):
    def __init__(self, response: str | list[str]) -> None:
        super().__init__(Settings(hermes_enabled=True, deepseek_api_key="test"))
        self.responses = response if isinstance(response, list) else [response]
        self.prompts: list[str] = []
        self.task_ids: list[str] = []

    def available(self) -> bool:
        return True

    async def run(self, prompt: str, system_message: str, task_id: str, enabled_toolsets: list[str] | None = None) -> str:
        self.prompts.append(prompt)
        self.task_ids.append(task_id)
        index = min(len(self.prompts) - 1, len(self.responses) - 1)
        return self.responses[index]


@pytest.mark.asyncio
async def test_l2_supervisor_rejects_unknown_worker() -> None:
    supervisor = L2Supervisor(
        FakeHermes(
            '{"action":"spawn_tasks","tasks":[{"task_type":"bad","worker_profile":"unknown","goal":"x","inputs":{},"artifact_type":"generic"}]}'
        ),
        max_repair_attempts=0,
    )

    with pytest.raises(ValueError, match="not allowed"):
        await supervisor.next_action(process_pack(), worker_profiles(), {"goal": "x"}, 0)


@pytest.mark.asyncio
async def test_l2_supervisor_enforces_task_limit() -> None:
    supervisor = L2Supervisor(
        FakeHermes(
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {"task_type":"a","worker_profile":"signal-collector","goal":"a","inputs":{"signals":["a"]},"artifact_type":"signals"},
                {"task_type":"b","worker_profile":"narrative-synthesizer","goal":"b","inputs":{"signals":[]},"artifact_type":"content_atoms"}
              ]
            }
            """
        ),
        max_repair_attempts=0,
    )

    with pytest.raises(ValueError, match="too many"):
        await supervisor.next_action(process_pack(), worker_profiles(), {"goal": "x"}, 0)


@pytest.mark.asyncio
async def test_l2_supervisor_repairs_malformed_output() -> None:
    hermes = FakeHermes(
        [
            "not json",
            '{"action":"message_user","message":"Need explicit signals.","tasks":[]}',
        ]
    )
    supervisor = L2Supervisor(hermes)

    action = await supervisor.next_action(process_pack(), worker_profiles(), {"goal": "x"}, 0)

    assert action.action == "message_user"
    assert len(hermes.prompts) == 2
    assert "Repair the previous L2 supervisor action" in hermes.prompts[1]


@pytest.mark.asyncio
async def test_l3_executor_rejects_missing_required_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = tmp_path / "bad_worker.py"
    module_path.write_text("import json, sys; json.loads(sys.stdin.read()); print('{}')", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    contract = TaskContract(
        run_id="00000000-0000-0000-0000-000000000000",
        task_type="collect",
        goal="collect",
        worker_profile="bad-worker",
        output_schema={"type": "object", "required": ["signals"]},
        budget={"max_seconds": 5},
    )

    with pytest.raises(L3WorkerExecutionError, match="missing required"):
        await L3SandboxExecutor().run(contract, {"goal": "goal"}, {"worker_type": "sandboxed_subprocess", "entrypoint": "bad_worker"})


@pytest.mark.asyncio
async def test_l3_executor_runs_hermes_agent_worker() -> None:
    hermes = FakeHermes('{"content_atoms":[{"claim":"done"}]}')
    contract = TaskContract(
        run_id="00000000-0000-0000-0000-000000000000",
        task_type="synthesize",
        goal="synthesize",
        worker_profile="narrative-synthesizer",
        worker_type="hermes_agent",
        inputs={"signals": [{"text": "done"}]},
        output_schema={"type": "object", "required": ["content_atoms"]},
    )

    payload = await L3SandboxExecutor(hermes).run(contract, {}, {"worker_type": "hermes_agent"})

    assert payload["content_atoms"][0]["claim"] == "done"
    assert payload["_worker_execution"]["mode"] == "hermes_agent"
