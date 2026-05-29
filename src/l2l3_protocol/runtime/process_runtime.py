from __future__ import annotations

import json
from typing import Any
from uuid import UUID

from l2l3_protocol.core.schemas import Artifact, ArtifactType, EvalResult, ImprovementProposalStatus, MemoryLayer, MemoryWrite, RegistryKind, RunMode, RunStatus, TaskStatus, WorkOrder
from l2l3_protocol.core.terminology import INCIDENT_BRIEF_EVENT
from l2l3_protocol.db.store import WorkingMemoryStore
from l2l3_protocol.logging import get_logger
from l2l3_protocol.memory.adapters import MemoryRouter, ProceduralRegistry
from l2l3_protocol.runtime.work_orders import WorkOrderValidationError, validate_work_order_inputs, validate_work_order_output, validate_tool_policy
from l2l3_protocol.runtime.diagnostics import analyze_run
from l2l3_protocol.runtime.self_improvement import build_failure_learnings
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.l2_design_controller import L2DesignController
from l2l3_protocol.runtime.l2_supervisor import L2Supervisor
from l2l3_protocol.runtime.l3_executor import L3SandboxExecutor, L3WorkerExecutionError

logger = get_logger("protocol.runtime")


class ProcessRuntime:
    def __init__(
        self,
        store: WorkingMemoryStore,
        registry: ProceduralRegistry,
        memory: MemoryRouter,
        hermes: HermesRuntime,
    ) -> None:
        self.store = store
        self.registry = registry
        self.memory = memory
        self.hermes = hermes
        self.supervisor = L2Supervisor(hermes)
        self.design_controller = L2DesignController(hermes)
        self.l3 = L3SandboxExecutor(hermes)

    async def run_until_blocked_or_done(self, run_id: UUID) -> dict[str, Any]:
        state = await self.store.get_run(run_id)
        if state is None:
            raise KeyError(f"run not found: {run_id}")
        mode = RunMode(state["l2_mode"])
        await self.store.add_event(run_id, "mode_selected", {"l2_mode": mode.value, "playbook_key": state["playbook_key"]})
        if mode == RunMode.DESIGN:
            await self._run_design_mode(run_id, state)
            return await self._require_run(run_id)

        playbook = await self._load_playbook(state["playbook_key"])
        worker_profiles = await self._allowed_worker_profiles(playbook)
        max_turns = int(playbook.get("max_supervisor_turns", 8))
        input_error = self._run_input_error(state, worker_profiles)
        if input_error is not None:
            await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": input_error})
            await self.store.add_event(run_id, "run_input_validation_failed", {"error": input_error, "failure_type": "input_validation"})
            await self.store.add_event(run_id, "run_failed", {"reason": input_error})
            await self._record_run_diagnosis(run_id)
            return await self._require_run(run_id)
        await self.store.set_run_status(run_id, RunStatus.RUNNING)
        if not any(event.get("event_type") == "run_started" for event in state.get("events", [])):
            await self.store.add_event(run_id, "run_started", {"playbook_key": state["playbook_key"], "goal": state["goal"], "l2_mode": mode.value})

        if playbook.get("execution_strategy") == "deterministic_p1_operator_outreach":
            await self._run_p1_operator_workflow(run_id, playbook, worker_profiles)
            await self._record_run_diagnosis(run_id)
            return await self._require_run(run_id)

        for turn in range(max_turns):
            current_status = await self.store.get_run_status(run_id)
            if current_status in {RunStatus.PAUSED, RunStatus.CANCELLED, RunStatus.COMPLETED, RunStatus.FAILED, RunStatus.WAITING_USER}:
                break
            state = await self.store.get_run(run_id)
            if state is None:
                raise KeyError(f"run not found: {run_id}")
            goal_discovery_output = self._goal_discovery_waiting_output(playbook, state)
            if goal_discovery_output is not None:
                await self.store.set_run_status(run_id, RunStatus.WAITING_USER, goal_discovery_output)
                await self.store.add_event(run_id, "l2_message_user", goal_discovery_output)
                break
            stop_reason = self._repair_stop_reason(state)
            if stop_reason is not None:
                await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": stop_reason})
                await self.store.add_event(run_id, "repair_budget_exhausted", {"reason": stop_reason})
                await self.store.add_event(run_id, "run_failed", {"reason": stop_reason})
                break
            action = await self.supervisor.next_action(playbook, worker_profiles, state, turn)
            await self.store.add_event(run_id, "l2_action_selected", action.model_dump(mode="json"))

            if action.action == "spawn_tasks":
                for task in action.tasks:
                    await self._execute_task(run_id, task.model_dump(mode="json"), worker_profiles[task.worker_profile])
                continue
            if action.action == "message_user":
                output = {"message": action.message}
                if action.interaction is not None:
                    output["interaction"] = action.interaction.model_dump(mode="json")
                await self.store.set_run_status(run_id, RunStatus.WAITING_USER, output)
                await self.store.add_event(run_id, "l2_message_user", output)
                break
            if action.action == "finish":
                await self._persist_learnings(run_id, action.output.get("memory_writes", []))
                await self.store.set_run_status(run_id, RunStatus.WAITING_APPROVAL if self._requires_approval(state) else RunStatus.COMPLETED, action.output)
                await self.store.add_event(run_id, "run_finished", {"status": (await self.store.get_run_status(run_id)).value})
                break
            if action.action == "fail":
                await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": action.reason})
                await self.store.add_event(run_id, "run_failed", {"reason": action.reason})
                break
            if action.action == "propose_registry_change":
                if action.registry_change_candidate is None:
                    raise ValueError("propose_registry_change requires registry_change_candidate")
                await self._record_registry_candidate(run_id, action.registry_change_candidate)
                await self.store.set_run_status(run_id, RunStatus.WAITING_APPROVAL)
                break
            if action.action == "propose_playbook":
                if action.playbook_proposal is None:
                    raise ValueError("propose_playbook requires playbook_proposal")
                await self._record_playbook_proposal(run_id, action.playbook_proposal)
                await self.store.set_run_status(run_id, RunStatus.WAITING_APPROVAL)
                break
        else:
            await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": "max_supervisor_turns exceeded"})
            await self.store.add_event(run_id, "run_failed", {"reason": "max_supervisor_turns exceeded"})

        await self._record_run_diagnosis(run_id)
        return await self._require_run(run_id)

    async def resume_with_message(self, run_id: UUID, message: str) -> dict[str, Any]:
        await self.store.add_event(run_id, "user_message", {"message": message})
        await self.store.set_run_status(run_id, RunStatus.RUNNING)
        return await self.run_until_blocked_or_done(run_id)

    async def apply_control(self, run_id: UUID, action: str, payload: dict[str, Any]) -> dict[str, Any]:
        if action == "pause":
            await self.store.set_run_status(run_id, RunStatus.PAUSED)
        elif action == "resume":
            await self.store.set_run_status(run_id, RunStatus.RUNNING)
            return await self.run_until_blocked_or_done(run_id)
        elif action == "stop":
            await self.store.set_run_status(run_id, RunStatus.CANCELLED)
        elif action == "approve":
            await self.store.set_run_status(run_id, RunStatus.COMPLETED)
        elif action == "reject":
            reason = payload["reason"]
            await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": reason})
        elif action == "request_edit":
            message = payload["message"]
            state = await self._require_run(run_id)
            await self.store.set_run_status(run_id, RunStatus.WAITING_USER, {**state.get("output", {}), "requested_edit": message})
        else:
            raise ValueError(f"unknown control action: {action}")
        await self.store.add_event(run_id, "run_control", {"action": action, "payload": payload})
        return await self._require_run(run_id)

    async def _execute_task(self, run_id: UUID, task: dict[str, Any], profile: dict[str, Any]) -> None:
        task_inputs = await self._inputs_with_implemented_improvements(task)
        work_order = WorkOrder(
            run_id=run_id,
            task_type=task["task_type"],
            goal=task["goal"],
            worker_profile=task["worker_profile"],
            worker_type=profile.get("worker_type", "sandboxed_subprocess"),
            inputs=task_inputs,
            output_schema=profile.get("output_schema", {}),
            allowed_tools=profile.get("allowed_tools", []),
            budget=profile.get("budget", {}),
            stop_conditions=profile.get("stop_conditions", []),
            grader_spec=profile.get("grader_spec", {}),
            retry_policy=profile.get("retry_policy", {}),
            memory_policy=profile.get("memory_policy", {}),
            external_action_policy=profile.get("external_action_policy", {}),
        )
        if task.get("allowed_tools"):
            work_order.allowed_tools = task["allowed_tools"]
        await self.store.add_task(work_order)
        await self.store.add_event(run_id, "task_created", {"task_type": work_order.task_type, "worker_profile": work_order.worker_profile}, work_order.id)
        try:
            validate_work_order_inputs(work_order, profile)
            playbook = await self._load_playbook((await self._require_run(run_id))["playbook_key"])
            resolved_tools = validate_tool_policy(work_order, profile, playbook, await self._tool_specs())
            if resolved_tools:
                work_order.allowed_tools = resolved_tools
        except WorkOrderValidationError as exc:
            await self.store.set_task_status(work_order.id, TaskStatus.FAILED)
            await self.store.add_event(run_id, "work_order_validation_failed", {"error": str(exc), "failure_type": exc.failure_type}, work_order.id)
            await self.store.add_event(run_id, "task_failed", {"error": str(exc), "worker_profile": work_order.worker_profile}, work_order.id)
            await self._record_failure_context(run_id, work_order.id, work_order, profile, exc.failure_type, str(exc))
            return
        await self.store.set_task_status(work_order.id, TaskStatus.RUNNING)
        state = await self._require_run(run_id)
        try:
            payload = await self.l3.run(work_order, state, profile)
        except L3WorkerExecutionError as exc:
            await self.store.set_task_status(work_order.id, TaskStatus.FAILED)
            await self.store.add_event(run_id, "task_failed", {"error": str(exc), "worker_profile": work_order.worker_profile}, work_order.id)
            await self._record_failure_context(run_id, work_order.id, work_order, profile, self._classify_worker_error(exc), str(exc))
            return
        try:
            validate_work_order_output(work_order, payload)
        except WorkOrderValidationError as exc:
            await self.store.set_task_status(work_order.id, TaskStatus.FAILED)
            await self.store.add_event(run_id, "work_order_output_validation_failed", {"error": str(exc), "failure_type": exc.failure_type}, work_order.id)
            await self._record_failure_context(run_id, work_order.id, work_order, profile, exc.failure_type, str(exc))
            return
        await self.store.set_task_status(work_order.id, TaskStatus.COMPLETED)
        artifact_type = self._artifact_type_for_task(task, work_order, payload)
        if work_order.worker_profile == "approval-adapter":
            artifact_type = ArtifactType.APPROVAL_DECISION
        artifact = Artifact(run_id=run_id, task_id=work_order.id, artifact_type=artifact_type, payload=payload)
        await self.store.add_artifact(artifact)
        await self.store.add_event(run_id, "task_completed", {"artifact_type": artifact_type.value}, work_order.id)
        if work_order.grader_spec:
            eval_result = await self._record_eval(run_id, work_order.id, work_order, payload)
            if not eval_result.passed:
                await self.store.set_task_status(work_order.id, TaskStatus.FAILED)
                await self.store.add_event(run_id, "task_eval_failed", eval_result.model_dump(mode="json"), work_order.id)
                await self._record_failure_context(run_id, work_order.id, work_order, profile, "eval_failed", "eval did not meet threshold", eval_result)

    async def _run_p1_operator_workflow(
        self,
        run_id: UUID,
        playbook: dict[str, Any],
        worker_profiles: dict[str, dict[str, Any]],
    ) -> None:
        state = await self._require_run(run_id)
        inputs = state.get("input", {}).get("inputs", {})
        if not isinstance(inputs, dict):
            await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": "p1 inputs must be an object"})
            await self.store.add_event(run_id, "run_failed", {"reason": "p1 inputs must be an object"})
            return
        mode = str(inputs.get("mode") or "existing_dossiers")
        await self.store.add_event(run_id, "p1_workflow_started", {"mode": mode})

        async def run_task(worker: str, task_type: str, task_inputs: dict[str, Any], artifact_type: ArtifactType) -> bool:
            profile = worker_profiles[worker]
            await self._execute_task(
                run_id,
                {
                    "task_type": task_type,
                    "worker_profile": worker,
                    "goal": profile.get("description", task_type),
                    "inputs": task_inputs,
                    "artifact_type": artifact_type.value,
                    "allowed_tools": profile.get("allowed_tools", []),
                },
                profile,
            )
            latest = await self._require_run(run_id)
            failed = [
                task
                for task in latest.get("tasks", [])
                if task.get("worker_profile") == worker and task.get("status") in {TaskStatus.FAILED.value, TaskStatus.NEEDS_REPAIR.value}
            ]
            return not failed

        if mode in {"existing_dossiers", "outreach_only"}:
            if not await run_task("p1-dossier-reader", "read_existing_dossiers", inputs, ArtifactType.P1_DOSSIERS):
                await self._fail_p1_if_needed(run_id, "p1 existing dossier read failed")
                return
        elif mode in {"full_pipeline", "source_only"}:
            if not await run_task("p1-source-collector", "collect_sources", inputs, ArtifactType.P1_LEAD_CANDIDATES):
                await self._fail_p1_if_needed(run_id, "p1 source collection failed")
                return
            candidates = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_LEAD_CANDIDATES)
            if not await run_task("p1-lead-normalizer", "normalize_leads", {"lead_candidates": candidates.get("lead_candidates", [])}, ArtifactType.P1_NORMALIZED_LEADS):
                await self._fail_p1_if_needed(run_id, "p1 lead normalization failed")
                return
            normalized = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_NORMALIZED_LEADS)
            if not await run_task("p1-triage-scorer", "score_triage", {"normalized_leads": normalized.get("normalized_leads", [])}, ArtifactType.P1_TRIAGE_SCORES):
                await self._fail_p1_if_needed(run_id, "p1 triage scoring failed")
                return
            scores = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_TRIAGE_SCORES)
            if not await run_task("p1-dossier-writer", "write_dossiers", {**inputs, "triage_scores": scores.get("triage_scores", [])}, ArtifactType.P1_DOSSIERS):
                await self._fail_p1_if_needed(run_id, "p1 dossier writing failed")
                return
            if mode == "source_only":
                await self.store.set_run_status(run_id, RunStatus.COMPLETED, {"mode": mode, "message": "P1 source-only workflow completed."})
                await self.store.add_event(run_id, "run_finished", {"status": RunStatus.COMPLETED.value})
                return
        else:
            await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": f"unsupported p1 mode: {mode}"})
            await self.store.add_event(run_id, "run_failed", {"reason": f"unsupported p1 mode: {mode}"})
            return

        dossiers = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_DOSSIERS)
        if not await run_task("p1-live-intel-gatherer", "gather_live_intelligence", {**inputs, "p1_dossiers": dossiers.get("p1_dossiers", [])}, ArtifactType.P1_LIVE_INTELLIGENCE):
            await self._fail_p1_if_needed(run_id, "p1 live intelligence failed")
            return
        live_intel = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_LIVE_INTELLIGENCE)
        if not await run_task("p1-gateway-evaluator", "evaluate_gateway", {"p1_dossiers": live_intel.get("p1_dossiers", [])}, ArtifactType.P1_GATEWAY_EVALUATIONS):
            await self._fail_p1_if_needed(run_id, "p1 gateway evaluation failed")
            return
        gateway = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_GATEWAY_EVALUATIONS)
        if not await run_task("p1-forge-queue-builder", "build_forge_queue", {"gateway_evaluations": gateway.get("gateway_evaluations", [])}, ArtifactType.P1_FORGE_QUEUE):
            await self._fail_p1_if_needed(run_id, "p1 forge queue failed")
            return
        queue = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_FORGE_QUEUE)
        if not await run_task("p1-outreach-draft-writer", "write_outreach_drafts", {"forge_queue": queue.get("forge_queue", []), "channels": inputs.get("channels", ["linkedin"])}, ArtifactType.P1_OUTREACH_DRAFTS):
            await self._fail_p1_if_needed(run_id, "p1 outreach drafting failed")
            return
        drafts = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_OUTREACH_DRAFTS)
        if not await run_task("p1-outreach-quality-judge", "judge_outreach_quality", {"outreach_drafts": drafts.get("outreach_drafts", [])}, ArtifactType.P1_OUTREACH_APPROVAL_PACKAGE):
            await self._fail_p1_if_needed(run_id, "p1 outreach quality failed")
            return
        approval_package = self._latest_payload(await self._require_run(run_id), ArtifactType.P1_OUTREACH_APPROVAL_PACKAGE)
        allow_sheet_write = bool(inputs.get("allow_google_sheet_write", False))
        approval_required = self._requires_approval(await self._require_run(run_id))
        external_sync_performed = False
        if allow_sheet_write and approval_required:
            await self.store.add_event(
                run_id,
                "p1_external_sync_waiting_approval",
                {
                    "reason": "Google Sheets write is an external action and requires approval before execution.",
                    "requested_worker": "p1-google-sheets-syncer",
                },
            )
        elif allow_sheet_write:
            if not await run_task("p1-google-sheets-syncer", "sync_google_sheets", {**inputs, **approval_package}, ArtifactType.P1_EXTERNAL_SYNC_RESULT):
                await self._fail_p1_if_needed(run_id, "p1 Google Sheets sync failed")
                return
            external_sync_performed = True
        await self.store.set_run_status(
            run_id,
            RunStatus.WAITING_APPROVAL if approval_required else RunStatus.COMPLETED,
            {
                "mode": mode,
                "approval_package": approval_package,
                "external_sync_requested": allow_sheet_write,
                "external_sync_performed": external_sync_performed,
            },
        )
        await self.store.add_event(run_id, "run_finished", {"status": (await self.store.get_run_status(run_id)).value})

    @staticmethod
    def _latest_payload(state: dict[str, Any], artifact_type: ArtifactType) -> dict[str, Any]:
        for artifact in reversed(state.get("artifacts", [])):
            if artifact.get("artifact_type") == artifact_type.value:
                payload = artifact.get("payload", {})
                return payload if isinstance(payload, dict) else {}
        return {}

    async def _fail_p1_if_needed(self, run_id: UUID, reason: str) -> None:
        current = await self.store.get_run_status(run_id)
        if current not in {RunStatus.FAILED, RunStatus.CANCELLED}:
            await self.store.set_run_status(run_id, RunStatus.FAILED, {"reason": reason})
            await self.store.add_event(run_id, "run_failed", {"reason": reason})

    async def _inputs_with_implemented_improvements(self, task: dict[str, Any]) -> dict[str, Any]:
        inputs = dict(task.get("inputs", {}))
        if task.get("worker_profile") != "trend-source-collector":
            return inputs
        requested_providers = inputs.get("providers")
        if not isinstance(requested_providers, list) or not requested_providers:
            return inputs
        requested = {"huggingface" if str(provider).lower() == "hf" else str(provider).lower() for provider in requested_providers}
        implemented = await self.store.list_improvement_proposals(status=ImprovementProposalStatus.IMPLEMENTED)
        proven = await self.store.list_improvement_proposals(status=ImprovementProposalStatus.PROVEN)
        provider_proposals: list[tuple[str, str]] = []
        for proposal in implemented + proven:
            if proposal.failure_signature != "provider_no_results:trend-source-collector":
                continue
            if not proposal.target_component.startswith("trend-source-collector/provider:"):
                continue
            provider = proposal.target_component.rsplit(":", 1)[-1].lower()
            provider = "huggingface" if provider == "hf" else provider
            if provider in requested:
                provider_proposals.append((provider, str(proposal.id)))
        if not provider_proposals:
            return inputs
        inputs["approved_provider_auto_repairs"] = {
            "providers": sorted({provider for provider, _proposal_id in provider_proposals}),
            "source_proposal_ids": sorted({proposal_id for _provider, proposal_id in provider_proposals}),
        }
        return inputs

    async def _record_eval(self, run_id: UUID, task_id: UUID, work_order: WorkOrder, payload: dict[str, Any]) -> EvalResult:
        eval_key = work_order.grader_spec.get("eval_key")
        eval_spec = await self._load_eval_spec(eval_key) if eval_key else {}
        threshold = float(eval_spec.get("minimum_score", eval_spec.get("pass_threshold", 1.0)))
        score = float(payload.get("score", 0.0))
        worker_passed = bool(payload.get("passed", score >= threshold))
        passed = worker_passed and score >= threshold
        checks = {**payload.get("checks", {}), "threshold": threshold, "worker_passed": worker_passed}
        eval_result = EvalResult(
            run_id=run_id,
            task_id=task_id,
            passed=passed,
            score=score,
            reasons=payload.get("reasons", []),
            checks=checks,
            eval_key=eval_key,
            eval_type=eval_spec.get("eval_type", "unit"),
            threshold=threshold,
        )
        await self.store.add_eval(eval_result)
        return eval_result

    async def _record_registry_candidate(self, run_id: UUID, candidate: dict[str, Any]) -> None:
        artifact = Artifact(run_id=run_id, artifact_type=ArtifactType.REGISTRY_CHANGE_CANDIDATE, payload=candidate)
        await self.store.add_artifact(artifact)
        await self.store.add_event(run_id, "registry_change_candidate_created", candidate)

    async def _record_playbook_proposal(self, run_id: UUID, proposal: dict[str, Any]) -> None:
        artifact = Artifact(run_id=run_id, artifact_type=ArtifactType.PLAYBOOK_PROPOSAL, payload=proposal)
        await self.store.add_artifact(artifact)
        await self.store.add_event(run_id, "playbook_proposal_created", proposal)

    async def _record_run_diagnosis(self, run_id: UUID) -> None:
        state = await self._require_run(run_id)
        diagnosis, proposals = analyze_run(state)
        await self.store.add_artifact(diagnosis)
        await self.store.add_event(run_id, "run_diagnosis_created", diagnosis.payload)
        for proposal in proposals:
            await self.store.add_improvement_proposal(proposal)
            await self.store.add_event(run_id, "improvement_proposal_created", proposal.model_dump(mode="json"))
        learnings = await self.store.record_failure_learnings(build_failure_learnings(state, diagnosis.payload, proposals))
        for learning in learnings:
            await self.store.add_event(run_id, "failure_learning_recorded", learning.model_dump(mode="json"))

    async def _run_design_mode(self, run_id: UUID, state: dict[str, Any]) -> None:
        await self.store.set_run_status(run_id, RunStatus.RUNNING)
        await self.store.add_event(run_id, "design_started", {"playbook_key": state["playbook_key"], "goal": state["goal"]})
        proposal = await self.design_controller.propose_playbook(state, await self._hub_snapshot())
        payload = proposal.model_dump(mode="json")
        await self._record_playbook_proposal(run_id, payload)
        for candidate in payload.get("registry_change_candidates", []):
            await self._record_registry_candidate(run_id, candidate)
            await self.store.add_event(run_id, "design_candidate_created", candidate)
        await self.store.set_run_status(run_id, RunStatus.WAITING_APPROVAL, {"design_proposal": payload})

    @staticmethod
    def _repair_stop_reason(state: dict[str, Any]) -> str | None:
        latest_incident: dict[str, Any] | None = None
        for event in reversed(state.get("events", [])):
            if event.get("event_type") != INCIDENT_BRIEF_EVENT:
                continue
            payload = event.get("payload", {})
            if isinstance(payload, dict):
                latest_incident = payload
            break
        if latest_incident is None:
            return None
        if int(latest_incident.get("retry_count_remaining", 1) or 0) > 0:
            return None
        worker = str(latest_incident.get("worker_profile") or "unknown-worker")
        failure_type = str(latest_incident.get("failure_type") or "unknown_failure")
        return f"repair budget exhausted for {worker}/{failure_type}"

    @staticmethod
    def _run_input_error(state: dict[str, Any], worker_profiles: dict[str, dict[str, Any]]) -> str | None:
        if state.get("playbook_key") != "build-in-public-trend-radar":
            return None
        providers = state.get("input", {}).get("inputs", {}).get("providers", [])
        if not isinstance(providers, list):
            return "trend-radar input.providers must be a list"
        collector = worker_profiles.get("trend-source-collector", {})
        supported = set((collector.get("provider_repair_policy", {}).get("provider_capabilities") or {}).keys())
        if not supported:
            return "trend-source-collector provider capabilities are missing"
        requested = {str(provider).lower() for provider in providers}
        unsupported = sorted(requested - supported)
        if unsupported:
            return f"unsupported providers requested: {unsupported}; supported providers: {sorted(supported)}"
        return None

    async def _hub_snapshot(self) -> dict[str, Any]:
        return {
            "playbooks": [item.model_dump(mode="json") for item in await self.store.list_registry_items(RegistryKind.PLAYBOOK)],
            "workers": [item.model_dump(mode="json") for item in await self.store.list_registry_items(RegistryKind.WORKER)],
            "tools": [item.model_dump(mode="json") for item in await self.store.list_registry_items(RegistryKind.TOOL)],
            "evals": [item.model_dump(mode="json") for item in await self.store.list_registry_items(RegistryKind.EVAL)],
            "failure_patterns": [item.model_dump(mode="json") for item in await self.store.list_registry_items(RegistryKind.FAILURE_PATTERN)],
        }

    async def _persist_learnings(self, run_id: UUID, writes: list[dict[str, Any]]) -> None:
        for item in writes:
            layer = MemoryLayer(item.get("layer", "episodic"))
            if layer not in {MemoryLayer.EPISODIC, MemoryLayer.SEMANTIC}:
                continue
            await self.memory.write(
                MemoryWrite(
                    layer=layer,
                    run_id=run_id,
                    content=item["content"],
                    metadata=item.get("metadata", {}),
                )
            )

    async def _load_playbook(self, key: str) -> dict[str, Any]:
        item = await self.store.get_registry_item(RegistryKind.PLAYBOOK, key)
        if item is None:
            raise KeyError(f"Taskforce Hub playbook is not seeded: {key}")
        return item.spec

    async def _load_eval_spec(self, key: str) -> dict[str, Any]:
        item = await self.store.get_registry_item(RegistryKind.EVAL, key)
        if item is None:
            raise KeyError(f"registry eval is not seeded: {key}")
        return item.spec

    async def _allowed_worker_profiles(self, playbook: dict[str, Any]) -> dict[str, dict[str, Any]]:
        profiles = await self._worker_profiles()
        allowed = playbook.get("allowed_workers", [])
        if not allowed:
            raise ValueError("playbook must define allowed_workers")
        missing = [key for key in allowed if key not in profiles]
        if missing:
            raise ValueError(f"playbook references missing worker profiles: {missing}")
        return {key: profiles[key] for key in allowed}

    async def _worker_profiles(self) -> dict[str, dict[str, Any]]:
        items = await self.store.list_registry_items(RegistryKind.WORKER)
        if not items:
            raise KeyError("registry workers are not seeded")
        return {item.key: item.spec for item in items}

    async def _tool_specs(self) -> dict[str, dict[str, Any]]:
        items = await self.store.list_registry_items(RegistryKind.TOOL)
        return {item.key: item.spec for item in items}

    async def _record_failure_context(
        self,
        run_id: UUID,
        task_id: UUID,
        work_order: WorkOrder,
        profile: dict[str, Any],
        failure_type: str,
        error: str,
        eval_result: EvalResult | None = None,
    ) -> None:
        pattern = await self._match_failure_pattern(work_order.worker_profile, failure_type)
        retry_policy = work_order.retry_policy
        retryable = set(retry_policy.get("retryable_failure_types", [failure_type]))
        previous = await self._previous_failure_count(run_id, work_order.worker_profile, failure_type)
        max_attempts = int(retry_policy.get("max_attempts", 1))
        retry_count_remaining = max(0, max_attempts - previous - 1) if failure_type in retryable else 0
        payload = {
            "task_id": str(task_id),
            "worker_profile": work_order.worker_profile,
            "failure_type": failure_type,
            "error": error,
            "structured_error": self._structured_worker_error(error),
            "repair_policy": profile.get("provider_repair_policy") or profile.get("repair_policy") or {},
            "repair_guidance": self._repair_guidance(work_order, profile, failure_type, error),
            "matched_failure_pattern": pattern,
            "mitigation_applied": pattern.get("mitigation") if pattern else None,
            "retry_count_remaining": retry_count_remaining,
            "eval_result": eval_result.model_dump(mode="json") if eval_result else None,
        }
        if retry_count_remaining > 0:
            await self.store.set_task_status(task_id, TaskStatus.NEEDS_REPAIR)
        await self.store.add_event(run_id, INCIDENT_BRIEF_EVENT, payload, task_id)

    @staticmethod
    def _structured_worker_error(error: str) -> dict[str, Any] | None:
        try:
            parsed = json.loads(error)
        except Exception:
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _repair_guidance(work_order: WorkOrder, profile: dict[str, Any], failure_type: str, error: str) -> dict[str, Any]:
        provider_policy = profile.get("provider_repair_policy")
        if work_order.worker_profile != "trend-source-collector" or not provider_policy:
            return {
                "l2_can": [
                    "spawn a schema or eval-input normalizer task when artifacts can be adapted safely",
                    "spawn a repaired task using prior artifacts and stricter inputs",
                    "propose a registry_change_candidate when executable worker/profile behavior must change",
                    "fail explicitly if the failure is not repairable within policy",
                ],
                "escalate_to_user_only_for": [
                    "product/editorial tradeoff",
                    "external action",
                    "approval-required registry or executable behavior change",
                ],
                "failure_type": failure_type,
                "last_error": error,
            }
        return {
            "l2_can": [
                "retry the same provider with provider_repairs using alternative real queries",
                "retry a provider with a different supported resource_type if the provider supports it",
                "ask the user for repair direction if the needed choice is product/editorial",
                "propose a registry or worker code change candidate if the worker implementation appears wrong",
                "fail explicitly if a required provider cannot be repaired within policy budget",
            ],
            "example_repair_inputs": {
                "query": work_order.inputs.get("query"),
                "providers": work_order.inputs.get("providers"),
                "provider_repairs": {
                    "huggingface": [
                        {"strategy": "shorter_query", "query": "agent eval", "resource_type": "models"},
                        {"strategy": "broader_query", "query": "agent runtime", "resource_type": "datasets"},
                    ]
                },
            },
            "policy": provider_policy,
            "last_error": error,
            "failure_type": failure_type,
        }

    async def _previous_failure_count(self, run_id: UUID, worker_profile: str, failure_type: str) -> int:
        state = await self._require_run(run_id)
        count = 0
        seen: set[tuple[str | None, str]] = set()
        for event in state.get("events", []):
            if event.get("event_type") != INCIDENT_BRIEF_EVENT:
                continue
            payload = event.get("payload", {})
            dedupe_key = (event.get("task_id"), str(payload.get("failure_type", "")))
            if dedupe_key in seen:
                continue
            seen.add(dedupe_key)
            if payload.get("worker_profile") == worker_profile and payload.get("failure_type") == failure_type:
                count += 1
        return count

    async def _match_failure_pattern(self, worker_profile: str, failure_type: str) -> dict[str, Any] | None:
        items = await self.store.list_registry_items(RegistryKind.FAILURE_PATTERN)
        patterns = [item.spec for item in items]
        for pattern in patterns:
            if pattern.get("worker_id") in {None, worker_profile} and pattern.get("failure_type") == failure_type:
                return pattern
        return None

    async def _require_run(self, run_id: UUID) -> dict[str, Any]:
        state = await self.store.get_run(run_id)
        if state is None:
            raise KeyError(f"run not found: {run_id}")
        return state

    @staticmethod
    def _artifact_type_for_task(task: dict[str, Any], work_order: WorkOrder, payload: dict[str, Any]) -> ArtifactType:
        explicit = task.get("artifact_type")
        if isinstance(explicit, str) and explicit != ArtifactType.GENERIC.value:
            return ArtifactType(explicit)
        if work_order.worker_profile == "goal-hypothesis-generator" or "goal_hypotheses" in payload:
            return ArtifactType.GOAL_HYPOTHESES
        if work_order.worker_profile == "goal-brief-compiler" or "goal_brief" in payload:
            return ArtifactType.GOAL_BRIEF
        return ArtifactType(str(explicit or ArtifactType.GENERIC.value))

    @staticmethod
    def _goal_discovery_waiting_output(playbook: dict[str, Any], state: dict[str, Any]) -> dict[str, Any] | None:
        if str(playbook.get("goal_protocol") or "") != "unclear_goal":
            return None
        if any(event.get("event_type") == "user_message" for event in state.get("events", [])):
            return None
        artifact = _latest_artifact(state, ArtifactType.GOAL_HYPOTHESES.value)
        if artifact is None:
            return None
        payload = artifact.get("payload", {})
        if not isinstance(payload, dict):
            raise ValueError("goal-discovery goal_hypotheses artifact payload must be an object")
        interaction = _normalize_goal_interaction(payload.get("recommended_interaction"))
        return {
            "message": "I mapped the unclear goal into concrete paths. Pick the direction that matters first.",
            "interaction": interaction,
        }

    @staticmethod
    def _classify_worker_error(exc: L3WorkerExecutionError) -> str:
        message = str(exc).lower()
        compact_message = message.replace(" ", "")
        empty_provider_failures = '"provider_failures":{}' in compact_message or "'provider_failures':{}" in compact_message
        if "trend providers failed" in message or "all trend providers failed" in message:
            return "provider_request_failed"
        if "provider_failures" in message and not empty_provider_failures:
            return "provider_request_failed"
        if "timed out" in message:
            return "timeout"
        if "invalid json" in message:
            return "invalid_json"
        if "missing environment variable" in message or "missing provider credential" in message:
            return "missing_provider_credential"
        if "no gateway-approved" in message or "no eligible" in message or "empty forge queue" in message:
            return "no_eligible_candidates"
        if "no results" in message or "no lead candidates" in message or "returned no" in message:
            return "provider_no_results"
        if "missing required" in message:
            return "output_schema"
        return "worker_exception"

    @staticmethod
    def _requires_approval(state: dict[str, Any]) -> bool:
        return bool(state["input"]["require_human_approval"])


def _latest_artifact(state: dict[str, Any], artifact_type: str) -> dict[str, Any] | None:
    for artifact in reversed(state.get("artifacts", [])):
        if isinstance(artifact, dict) and artifact.get("artifact_type") == artifact_type:
            return artifact
    return None


def _normalize_goal_interaction(value: Any) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise ValueError("goal-discovery recommended_interaction must be an object")
    raw = value.get("goal_clarification") if isinstance(value.get("goal_clarification"), dict) else value
    kind = str(raw.get("kind") or "goal_clarification")
    question = raw.get("question") or raw.get("prompt")
    if kind != "goal_clarification":
        raise ValueError("goal-discovery recommended_interaction.kind must be goal_clarification")
    if not isinstance(question, str) or not question.strip():
        raise ValueError("goal-discovery recommended_interaction requires question or prompt")
    raw_options = raw.get("options")
    if not isinstance(raw_options, list) or len(raw_options) < 2 or len(raw_options) > 4:
        raise ValueError("goal-discovery recommended_interaction must include 2-4 options")
    options: list[dict[str, str]] = []
    for index, option in enumerate(raw_options):
        if not isinstance(option, dict):
            raise ValueError(f"goal-discovery recommended_interaction.options[{index}] must be an object")
        option_id = option.get("id") or option.get("option_id")
        label = option.get("label") or option.get("title")
        description = option.get("description") or option.get("outcome") or option.get("implies")
        if not isinstance(option_id, str) or not option_id.strip():
            raise ValueError(f"goal-discovery recommended_interaction.options[{index}] requires id or option_id")
        if not isinstance(label, str) or not label.strip():
            raise ValueError(f"goal-discovery recommended_interaction.options[{index}] requires label")
        if not isinstance(description, str) or not description.strip():
            raise ValueError(f"goal-discovery recommended_interaction.options[{index}] requires description, outcome, or implies")
        options.append({"id": option_id.strip(), "label": label.strip(), "description": description.strip()})
    output = {"kind": kind, "question": question.strip(), "options": options}
    if isinstance(raw.get("why_this_question"), str) and raw["why_this_question"].strip():
        output["why_this_question"] = raw["why_this_question"].strip()
    if isinstance(raw.get("resolution_hint"), str) and raw["resolution_hint"].strip():
        output["resolution_hint"] = raw["resolution_hint"].strip()
    return output
