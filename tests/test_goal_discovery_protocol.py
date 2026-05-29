from pathlib import Path
from typing import Any
from uuid import UUID

import pytest

from l2l3_protocol.config import Settings
from l2l3_protocol.core.schemas import Artifact, EvalResult, FailureLearning, ImprovementProposal, MemoryWrite, ProcessRun, RegistryItem, RegistryKind, RunStatus, TaskStatus, WorkOrder
from l2l3_protocol.hub.registry import yaml_registry_items
from l2l3_protocol.memory.adapters import ProceduralRegistry
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.l2_supervisor import L2Supervisor
from l2l3_protocol.runtime.process_runtime import ProcessRuntime, _normalize_goal_interaction


class FakeStore:
    def __init__(self, run: ProcessRun) -> None:
        self.run = run
        self.tasks: list[WorkOrder] = []
        self.artifacts: list[Artifact] = []
        self.evals: list[EvalResult] = []
        self.improvement_proposals: list[ImprovementProposal] = []
        self.failure_learnings: list[FailureLearning] = []
        self.events: list[dict[str, Any]] = []
        self.registry_items = yaml_registry_items(Path('registries'))

    async def create_run(self, run: ProcessRun) -> ProcessRun:
        self.run = run
        return run

    async def get_run_status(self, run_id: UUID) -> RunStatus:
        return self.run.status

    async def set_run_status(self, run_id: UUID, status: RunStatus, output: dict[str, Any] | None = None) -> None:
        self.run.status = status
        if output is not None:
            self.run.output = output

    async def get_run(self, run_id: UUID) -> dict[str, Any] | None:
        if run_id != self.run.id:
            return None
        return {
            'id': str(self.run.id),
            'playbook_key': self.run.playbook_key,
            'l2_mode': self.run.l2_mode.value,
            'goal': self.run.goal,
            'status': self.run.status.value,
            'input': self.run.input,
            'output': self.run.output,
            'tasks': [task.model_dump(mode='json') for task in self.tasks],
            'artifacts': [
                {
                    'id': str(artifact.id),
                    'task_id': str(artifact.task_id) if artifact.task_id else None,
                    'artifact_type': artifact.artifact_type.value,
                    'payload': artifact.payload,
                }
                for artifact in self.artifacts
            ],
            'evals': [item.model_dump(mode='json') for item in self.evals],
            'events': self.events,
            'diagnosis': next((artifact.payload for artifact in reversed(self.artifacts) if artifact.artifact_type.value == 'run_diagnosis'), None),
            'improvement_proposals': [proposal.model_dump(mode='json') for proposal in self.improvement_proposals],
            'failure_learnings': [learning.model_dump(mode='json') for learning in self.failure_learnings],
        }

    async def add_task(self, work_order: WorkOrder) -> WorkOrder:
        self.tasks.append(work_order)
        return work_order

    async def set_task_status(self, task_id: UUID, status: TaskStatus) -> None:
        for task in self.tasks:
            if task.id == task_id:
                task.status = status

    async def add_artifact(self, artifact: Artifact) -> Artifact:
        self.artifacts.append(artifact)
        return artifact

    async def add_eval(self, eval_result: EvalResult) -> EvalResult:
        self.evals.append(eval_result)
        return eval_result

    async def add_event(self, run_id: UUID, event_type: str, payload: dict[str, Any], task_id: UUID | None = None) -> None:
        self.events.append({'event_type': event_type, 'payload': payload, 'task_id': str(task_id) if task_id else None})

    async def add_improvement_proposal(self, proposal: ImprovementProposal) -> ImprovementProposal:
        self.improvement_proposals.append(proposal)
        return proposal

    async def record_failure_learnings(self, learnings: list[FailureLearning]) -> list[FailureLearning]:
        self.failure_learnings.extend(learnings)
        return learnings

    async def get_registry_item(self, kind: RegistryKind, key: str) -> RegistryItem | None:
        return next((item for item in self.registry_items if item.kind == kind and item.key == key), None)

    async def list_registry_items(self, kind: RegistryKind) -> list[RegistryItem]:
        return [item for item in self.registry_items if item.kind == kind]


class FakeMemory:
    def __init__(self) -> None:
        self.writes: list[MemoryWrite] = []

    async def write(self, write: MemoryWrite) -> None:
        self.writes.append(write)


class FakeHermes(HermesRuntime):
    def __init__(self, responses: list[str]) -> None:
        super().__init__(Settings(hermes_enabled=True, deepseek_api_key='test'))
        self.responses = responses
        self.calls = 0
        self.prompts: list[str] = []

    def available(self) -> bool:
        return True

    async def run(self, prompt: str, system_message: str, task_id: str, enabled_toolsets: list[str] | None = None) -> str:
        self.prompts.append(prompt)
        response = self.responses[min(self.calls, len(self.responses) - 1)]
        self.calls += 1
        return response


def goal_playbook() -> dict[str, Any]:
    return {
        'key': 'goal-discovery',
        'goal_protocol': 'unclear_goal',
        'allowed_workers': ['goal-hypothesis-generator', 'goal-brief-compiler', 'learning-worker'],
        'max_tasks_per_turn': 1,
    }


def goal_workers() -> dict[str, dict[str, Any]]:
    return {
        'goal-hypothesis-generator': {'worker_type': 'hermes_agent', 'output_schema': {'required': ['goal_hypotheses', 'recommended_interaction', 'ambiguity_summary']}},
        'goal-brief-compiler': {'worker_type': 'hermes_agent', 'output_schema': {'required': ['goal_brief']}},
        'learning-worker': {'worker_type': 'sandboxed_subprocess', 'output_schema': {'required': ['memory_writes', 'procedural_change_candidate']}},
    }


def test_goal_interaction_normalizer_accepts_real_nested_worker_shape() -> None:
    interaction = _normalize_goal_interaction(
        {
            'goal_clarification': {
                'prompt': 'Which path should we test next?',
                'options': [
                    {'option_id': 'a', 'label': 'Specific feature', 'implies': 'Create a concrete feature test brief.'},
                    {'option_id': 'b', 'label': 'Process template', 'outcome': 'Create a reusable testing process.'},
                ],
            }
        }
    )

    assert interaction['kind'] == 'goal_clarification'
    assert interaction['question'] == 'Which path should we test next?'
    assert interaction['options'][0]['id'] == 'a'
    assert interaction['options'][1]['description'] == 'Create a reusable testing process.'


@pytest.mark.asyncio
async def test_goal_discovery_requires_structured_interaction() -> None:
    hermes = FakeHermes(
        [
            '{"action":"message_user","message":"Pick one direction."}',
            '{"action":"message_user","message":"Pick one direction.","interaction":{"kind":"goal_clarification","question":"Which outcome matters most first?","options":[{"id":"ship","label":"Ship artifact","description":"Get to a concrete deliverable fast."},{"id":"explore","label":"Explore options","description":"Compare alternatives before execution."}]}}',
        ]
    )
    supervisor = L2Supervisor(hermes)
    state = {
        'goal': 'I know I need something with ABRT but not what yet.',
        'artifacts': [{'artifact_type': 'goal_hypotheses', 'payload': {'items': []}}],
        'events': [],
    }

    action = await supervisor.next_action(goal_playbook(), goal_workers(), state, 0)

    assert action.action == 'message_user'
    assert action.interaction is not None
    assert len(action.interaction.options) == 2
    assert 'goal-discovery protocol requires structured interaction' in hermes.prompts[1]


@pytest.mark.asyncio
async def test_goal_discovery_blocks_finish_without_goal_brief() -> None:
    supervisor = L2Supervisor(FakeHermes(['{"action":"finish","output":{"final":{"status":"done"}}}']), max_repair_attempts=0)

    with pytest.raises(ValueError, match='goal-discovery protocol cannot finish before goal_brief exists'):
        await supervisor.next_action(goal_playbook(), goal_workers(), {'goal': 'x', 'events': [], 'artifacts': []}, 0)


@pytest.mark.asyncio
async def test_runtime_records_structured_waiting_user_for_goal_discovery() -> None:
    run = ProcessRun(
        playbook_key='goal-discovery',
        goal='We need something useful for ABRT but the final artifact is unclear.',
        status=RunStatus.CREATED,
        input={
            'playbook_key': 'goal-discovery',
            'l2_mode': 'execution',
            'goal': 'We need something useful for ABRT but the final artifact is unclear.',
            'inputs': {'context': ['We want a high-signal next step for the team.']},
            'require_human_approval': False,
        },
    )
    hermes = FakeHermes(
        [
            '{"action":"spawn_tasks","tasks":[{"task_type":"generate_goal_hypotheses","worker_profile":"goal-hypothesis-generator","goal":"Generate goal hypotheses from the vague request.","inputs":{"goal":"We need something useful for ABRT but the final artifact is unclear.","context":["We want a high-signal next step for the team."]}}]}',
            '{"goal_hypotheses":[{"option_id":"ops","candidate_goal":"Build a launch-readiness proof pack.","deliverable":"A runnable proof pack script and readiness checklist.","assumptions":["The team wants operational confidence."],"success_signals":["A real run can be launched and verified."]},{"option_id":"product","candidate_goal":"Draft a user-facing goal-discovery flow.","deliverable":"A protocol and CLI flow for ambiguous intent.","assumptions":["The team wants a stronger intake path."],"success_signals":["Ambiguous requests become structured execution briefs."]}],"recommended_interaction":{"kind":"goal_clarification","question":"Which outcome matters more first?","options":[{"id":"ops","label":"Launch readiness","description":"Prioritize proof-pack and operational hardening."},{"id":"product","label":"Goal discovery UX","description":"Prioritize ambiguous-goal intake and clarification."}],"why_this_question":"The request mixes platform hardening and protocol design.","resolution_hint":"Reply with the option id and one sentence of context."},"ambiguity_summary":"The request contains both platform-hardening and product-protocol intent."}',
            '{"action":"spawn_tasks","tasks":[{"task_type":"compile_goal_brief","worker_profile":"goal-brief-compiler","goal":"Compile the clarified execution brief.","inputs":{"goal":"We need something useful for ABRT but the final artifact is unclear.","goal_hypotheses":[{"option_id":"ops","candidate_goal":"Build a launch-readiness proof pack."}],"user_reply":"ops"}}]}',
            '{"goal_brief":{"objective":"Build a launch-readiness proof pack.","clarified_outcome":"A concrete proof pack for ABRT.","success_criteria":["Real run passes"],"constraints":["Use real services"],"assumptions":["Ops path chosen"],"next_playbook_key":"build-in-public-trend-radar","recommended_inputs":["query"],"ready_for_execution":true}}',
            '{"action":"finish","output":{"final":{"ready_for_execution":true}}}',
        ]
    )
    store = FakeStore(run)

    output = await ProcessRuntime(store, ProceduralRegistry(Path('registries')), FakeMemory(), hermes).run_until_blocked_or_done(run.id)

    assert output['status'] == 'waiting_user'
    assert output['output']['interaction']['kind'] == 'goal_clarification'
    assert len(output['output']['interaction']['options']) == 2
    assert any(artifact.artifact_type.value == 'goal_hypotheses' for artifact in store.artifacts)
    assert output['diagnosis']['root_cause'] == 'none'
    assert output['improvement_proposals'] == []

    final = await ProcessRuntime(store, ProceduralRegistry(Path('registries')), FakeMemory(), hermes).resume_with_message(run.id, 'ops')

    assert final['status'] == 'completed'
    assert final['diagnosis']['outcome'] == 'completed'
    assert any(artifact.artifact_type.value == 'goal_brief' for artifact in store.artifacts)
