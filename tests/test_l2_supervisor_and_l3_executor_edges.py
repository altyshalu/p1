from pathlib import Path

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import WorkOrder
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.l2_supervisor import L2Supervisor
from l2l3_protocol.runtime.l3_executor import L3SandboxExecutor, L3WorkerExecutionError


def playbook() -> dict:
    return {
        "key": "build-in-public",
        "allowed_workers": ["signal-collector", "narrative-synthesizer", "approval-adapter"],
        "max_tasks_per_turn": 1,
        "required_eval_keys": ["quality"],
    }


def worker_profiles() -> dict:
    return {
        "signal-collector": {"worker_type": "sandboxed_subprocess", "output_schema": {"required": ["signals"]}},
        "narrative-synthesizer": {"worker_type": "hermes_agent", "output_schema": {"required": ["content_atoms"]}},
        "approval-adapter": {"worker_type": "human_gate", "output_schema": {"required": ["approval"]}},
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
        await supervisor.next_action(playbook(), worker_profiles(), {"goal": "x"}, 0)


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
        await supervisor.next_action(playbook(), worker_profiles(), {"goal": "x"}, 0)


@pytest.mark.asyncio
async def test_l2_supervisor_repairs_malformed_output() -> None:
    hermes = FakeHermes(
        [
            "not json",
            '{"action":"message_user","message":"Need explicit signals.","tasks":[]}',
        ]
    )
    supervisor = L2Supervisor(hermes)

    action = await supervisor.next_action(playbook(), worker_profiles(), {"goal": "x"}, 0)

    assert action.action == "message_user"
    assert len(hermes.prompts) == 2
    assert "Repair the previous L2 supervisor action" in hermes.prompts[1]


@pytest.mark.asyncio
async def test_l2_supervisor_blocks_internal_repair_escalation_to_user() -> None:
    hermes = FakeHermes(
        [
            '{"action":"message_user","message":"Should I respawn the judge and map evidence_urls to source_url?"}',
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "repair_claim_grounding_inputs",
                  "worker_profile": "narrative-synthesizer",
                  "goal": "Repair claim grounding inputs from existing draft artifacts.",
                  "inputs": {"drafts": []},
                  "artifact_type": "content_atoms"
                }
              ]
            }
            """,
        ]
    )
    supervisor = L2Supervisor(hermes)
    state = {
        "goal": "x",
        "events": [
            {
                "event_type": "incident_brief",
                "payload": {
                    "failure_type": "eval_failed",
                    "worker_profile": "claim-grounding-judge",
                    "retry_count_remaining": 0,
                    "repair_guidance": {"l2_can": ["map evidence_urls to source_url and retry judge"]},
                },
            }
        ],
    }

    action = await supervisor.next_action(playbook(), worker_profiles(), state, 0)

    assert action.action == "spawn_tasks"
    assert "message_user is not allowed for internal L2 repair mechanics" in hermes.prompts[1]


@pytest.mark.asyncio
async def test_l2_supervisor_blocks_finish_before_required_evals_pass() -> None:
    hermes = FakeHermes(
        [
            '{"action":"finish","output":{"final":{"note":"done"}}}',
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "repair",
                  "worker_profile": "narrative-synthesizer",
                  "goal": "Repair failed eval inputs.",
                  "inputs": {"signals": []},
                  "artifact_type": "content_atoms"
                }
              ]
            }
            """,
        ]
    )
    state = {"goal": "x", "evals": [{"eval_key": "quality", "passed": False}], "events": []}

    action = await L2Supervisor(hermes).next_action(playbook(), worker_profiles(), state, 0)

    assert action.action == "spawn_tasks"
    assert "finish is not allowed until required evals pass" in hermes.prompts[1]


@pytest.mark.asyncio
async def test_l2_supervisor_blocks_approval_before_required_evals_pass() -> None:
    hermes = FakeHermes(
        [
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "approve",
                  "worker_profile": "approval-adapter",
                  "goal": "Record approval gate.",
                  "inputs": {"require_human_approval": true},
                  "artifact_type": "generic"
                }
              ]
            }
            """,
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "repair",
                  "worker_profile": "narrative-synthesizer",
                  "goal": "Repair failed eval inputs.",
                  "inputs": {"signals": []},
                  "artifact_type": "content_atoms"
                }
              ]
            }
            """,
        ]
    )
    state = {"goal": "x", "evals": [{"eval_key": "quality", "passed": False}], "events": []}

    action = await L2Supervisor(hermes).next_action(playbook(), worker_profiles(), state, 0)

    assert action.action == "spawn_tasks"
    assert "approval-adapter is not allowed until required evals pass" in hermes.prompts[1]


@pytest.mark.asyncio
async def test_l2_supervisor_rejects_equivalent_duplicate_work_order() -> None:
    hermes = FakeHermes(
        [
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "collect",
                  "worker_profile": "signal-collector",
                  "goal": "Collect the same signals again.",
                  "inputs": {"signals": ["already handled"]},
                  "artifact_type": "signals"
                }
              ]
            }
            """,
            """
            {
              "action": "spawn_tasks",
              "tasks": [
                {
                  "task_type": "collect",
                  "worker_profile": "signal-collector",
                  "goal": "Collect changed signals.",
                  "inputs": {"signals": ["new evidence"]},
                  "artifact_type": "signals"
                }
              ]
            }
            """,
        ]
    )
    state = {
        "goal": "x",
        "tasks": [
            {
                "task_type": "collect",
                "worker_profile": "signal-collector",
                "inputs": {"signals": ["already handled"]},
                "status": "completed",
            }
        ],
        "events": [],
    }

    action = await L2Supervisor(hermes).next_action(playbook(), worker_profiles(), state, 0)

    assert action.tasks[0].inputs == {"signals": ["new evidence"]}
    assert "equivalent Work Order already exists" in hermes.prompts[1]


@pytest.mark.asyncio
async def test_l3_executor_rejects_missing_required_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    module_path = tmp_path / "bad_worker.py"
    module_path.write_text("import json, sys; json.loads(sys.stdin.read()); print('{}')", encoding="utf-8")
    monkeypatch.setenv("PYTHONPATH", str(tmp_path))
    work_order = WorkOrder(
        run_id="00000000-0000-0000-0000-000000000000",
        task_type="collect",
        goal="collect",
        worker_profile="bad-worker",
        output_schema={"type": "object", "required": ["signals"]},
        budget={"max_seconds": 5},
    )

    with pytest.raises(L3WorkerExecutionError, match="missing required"):
        await L3SandboxExecutor().run(work_order, {"goal": "goal"}, {"worker_type": "sandboxed_subprocess", "entrypoint": "bad_worker"})


@pytest.mark.asyncio
async def test_l3_executor_runs_hermes_agent_worker() -> None:
    hermes = FakeHermes('{"content_atoms":[{"claim":"done"}]}')
    work_order = WorkOrder(
        run_id="00000000-0000-0000-0000-000000000000",
        task_type="synthesize",
        goal="synthesize",
        worker_profile="narrative-synthesizer",
        worker_type="hermes_agent",
        inputs={"signals": [{"text": "done"}]},
        output_schema={"type": "object", "required": ["content_atoms"]},
    )

    payload = await L3SandboxExecutor(hermes).run(work_order, {}, {"worker_type": "hermes_agent"})

    assert payload["content_atoms"][0]["claim"] == "done"
    assert payload["_worker_execution"]["mode"] == "hermes_agent"


@pytest.mark.asyncio
async def test_l3_executor_runs_adapter_workers_via_sandbox() -> None:
    work_order = WorkOrder(
        run_id="00000000-0000-0000-0000-000000000000",
        task_type="normalize",
        goal="normalize draft",
        worker_profile="draft-schema-normalizer",
        worker_type="adapter",
        inputs={"drafts": [{"channel": "x", "thread": ["hello"], "claims": [{"text": "hello", "evidence_urls": ["https://e.test"]}]}]},
        output_schema={"type": "object", "required": ["drafts"]},
        budget={"max_seconds": 10},
    )

    payload = await L3SandboxExecutor().run(
        work_order,
        {},
        {"worker_type": "adapter", "entrypoint": "l2l3_protocol.workers.build_in_public_worker"},
    )

    assert payload["drafts"][0]["claims"][0]["source_url"] == "https://e.test"
