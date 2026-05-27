from typing import Any
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from l2l3_protocol.core.schemas import (
    Artifact,
    EvalResult,
    FailureLearning,
    FailureLearningStatus,
    ImprovementProposal,
    ImprovementProposalStatus,
    ProcessRun,
    RegistryChangeCandidate,
    RegistryChangeCandidateCreate,
    RegistryChangeStatus,
    RegistryItem,
    RegistryKind,
    RunStatus,
    SystemReview,
    TaskStatus,
    WorkOrder,
)
from l2l3_protocol.db.models import (
    ArtifactRecord,
    EvalResultRecord,
    EventRecord,
    FailureLearningRecord,
    ImprovementProposalRecord,
    ProcessRunRecord,
    RegistryChangeCandidateRecord,
    RegistryItemRecord,
    SystemReviewRecord,
    WorkOrderRecord,
)
from l2l3_protocol.hub.registry import apply_registry_change, is_safe_registry_change
from l2l3_protocol.runtime.self_improvement import proof_spec_for_proposal


class WorkingMemoryStore:
    def __init__(self, session: AsyncSession, auto_commit: bool = False) -> None:
        self.session = session
        self.auto_commit = auto_commit

    async def _persist(self) -> None:
        if self.auto_commit:
            await self.session.commit()
        else:
            await self.session.flush()

    async def create_run(self, run: ProcessRun) -> ProcessRun:
        record = ProcessRunRecord(
            id=run.id,
            playbook_key=run.playbook_key,
            l2_mode=run.l2_mode.value,
            goal=run.goal,
            status=run.status.value,
            input=run.input,
            output=run.output,
        )
        self.session.add(record)
        await self._persist()
        return run

    async def get_run(self, run_id: UUID) -> dict[str, Any] | None:
        record = await self.session.get(ProcessRunRecord, run_id)
        if record is None:
            return None
        tasks = (
            await self.session.execute(
                select(WorkOrderRecord).where(WorkOrderRecord.run_id == run_id).order_by(WorkOrderRecord.created_at)
            )
        ).scalars().all()
        artifacts = (
            await self.session.execute(select(ArtifactRecord).where(ArtifactRecord.run_id == run_id).order_by(ArtifactRecord.created_at))
        ).scalars().all()
        evals = (
            await self.session.execute(select(EvalResultRecord).where(EvalResultRecord.run_id == run_id).order_by(EvalResultRecord.created_at))
        ).scalars().all()
        events = (
            await self.session.execute(select(EventRecord).where(EventRecord.run_id == run_id).order_by(EventRecord.created_at))
        ).scalars().all()
        improvement_proposals = (
            await self.session.execute(
                select(ImprovementProposalRecord).where(ImprovementProposalRecord.run_id == run_id).order_by(ImprovementProposalRecord.created_at)
            )
        ).scalars().all()
        failure_learnings = (
            await self.session.execute(
                select(FailureLearningRecord)
                .where(FailureLearningRecord.last_seen_run_id == str(run_id))
                .order_by(FailureLearningRecord.updated_at)
            )
        ).scalars().all()
        artifacts_payload = [
            {
                "id": str(artifact.id),
                "task_id": str(artifact.task_id) if artifact.task_id else None,
                "artifact_type": artifact.artifact_type,
                "payload": artifact.payload,
            }
            for artifact in artifacts
        ]
        diagnoses = [artifact for artifact in artifacts_payload if artifact["artifact_type"] == "run_diagnosis"]
        return {
            "id": str(record.id),
            "playbook_key": record.playbook_key,
            "l2_mode": record.l2_mode,
            "goal": record.goal,
            "status": record.status,
            "input": record.input,
            "output": record.output,
            "created_at": record.created_at.isoformat() if record.created_at else None,
            "updated_at": record.updated_at.isoformat() if record.updated_at else None,
            "tasks": [task.work_order for task in tasks],
            "artifacts": artifacts_payload,
            "evals": [eval_record.payload for eval_record in evals],
            "events": [
                {
                    "event_type": event.event_type,
                    "task_id": str(event.task_id) if event.task_id else None,
                    "payload": event.payload,
                    "created_at": event.created_at.isoformat() if event.created_at else None,
                }
                for event in events
            ],
            "diagnosis": diagnoses[-1]["payload"] if diagnoses else None,
            "improvement_proposals": [self._improvement_proposal_from_record(record).model_dump(mode="json") for record in improvement_proposals],
            "failure_learnings": [self._failure_learning_from_record(record).model_dump(mode="json") for record in failure_learnings],
        }

    async def get_run_status(self, run_id: UUID) -> RunStatus:
        record = await self.session.get(ProcessRunRecord, run_id)
        if record is None:
            raise KeyError(f"run not found: {run_id}")
        return RunStatus(record.status)

    async def set_run_status(self, run_id: UUID, status: RunStatus, output: dict[str, Any] | None = None) -> None:
        record = await self.session.get(ProcessRunRecord, run_id)
        if record is None:
            raise KeyError(f"run not found: {run_id}")
        record.status = status.value
        if output is not None:
            record.output = output
        await self._persist()

    async def add_task(self, work_order: WorkOrder) -> WorkOrder:
        self.session.add(
            WorkOrderRecord(
                id=work_order.id,
                run_id=work_order.run_id,
                task_type=work_order.task_type,
                worker_profile=work_order.worker_profile,
                status=work_order.status.value,
                goal=work_order.goal,
                work_order=work_order.model_dump(mode="json"),
                created_at=datetime.now(UTC),
            )
        )
        await self._persist()
        return work_order

    async def update_run_input(self, run_id: UUID, input_patch: dict[str, Any]) -> None:
        record = await self.session.get(ProcessRunRecord, run_id)
        if record is None:
            raise KeyError(f"run not found: {run_id}")
        record.input = {**record.input, **input_patch}
        await self._persist()

    async def set_task_status(self, task_id: UUID, status: TaskStatus) -> None:
        record = await self.session.get(WorkOrderRecord, task_id)
        if record is None:
            raise KeyError(f"task not found: {task_id}")
        record.status = status.value
        record.work_order = {**record.work_order, "status": status.value}
        await self._persist()

    async def add_artifact(self, artifact: Artifact) -> Artifact:
        self.session.add(
            ArtifactRecord(
                id=artifact.id,
                run_id=artifact.run_id,
                task_id=artifact.task_id,
                artifact_type=artifact.artifact_type.value,
                payload=artifact.payload,
                created_at=datetime.now(UTC),
            )
        )
        await self._persist()
        return artifact

    async def add_eval(self, eval_result: EvalResult) -> EvalResult:
        self.session.add(
            EvalResultRecord(
                id=eval_result.id,
                run_id=eval_result.run_id,
                task_id=eval_result.task_id,
                passed=eval_result.passed,
                score=eval_result.score,
                payload=eval_result.model_dump(mode="json"),
                created_at=datetime.now(UTC),
            )
        )
        await self._persist()
        return eval_result

    async def add_event(self, run_id: UUID, event_type: str, payload: dict[str, Any], task_id: UUID | None = None) -> None:
        self.session.add(EventRecord(run_id=run_id, task_id=task_id, event_type=event_type, payload=payload, created_at=datetime.now(UTC)))
        await self._persist()

    async def add_improvement_proposal(self, proposal: ImprovementProposal) -> ImprovementProposal:
        record = ImprovementProposalRecord(
            id=proposal.id,
            run_id=proposal.run_id,
            source_run_id=proposal.source_run_id,
            proposal_type=proposal.proposal_type,
            target_component=proposal.target_component,
            failure_signature=proposal.failure_signature,
            problem=proposal.problem,
            proposed_change=proposal.proposed_change,
            risk=proposal.risk,
            success_check=proposal.success_check,
            evidence={"items": proposal.evidence},
            behavior_change_requires_approval=proposal.behavior_change_requires_approval,
            proof_spec=proposal.proof_spec,
            implementation_result=proposal.implementation_result,
            status=proposal.status.value,
            rejection_reason=proposal.rejection_reason,
            approved_at=proposal.approved_at,
            implemented_at=proposal.implemented_at,
            proven_at=proposal.proven_at,
            created_at=datetime.now(UTC),
        )
        self.session.add(record)
        await self._persist()
        return proposal

    async def list_improvement_proposals(
        self,
        status: ImprovementProposalStatus | None = None,
        run_id: UUID | None = None,
    ) -> list[ImprovementProposal]:
        statement = select(ImprovementProposalRecord).order_by(ImprovementProposalRecord.created_at)
        if status is not None:
            statement = statement.where(ImprovementProposalRecord.status == status.value)
        if run_id is not None:
            statement = statement.where(ImprovementProposalRecord.run_id == run_id)
        records = (await self.session.execute(statement)).scalars().all()
        return [self._improvement_proposal_from_record(record) for record in records]

    async def get_improvement_proposal(self, proposal_id: UUID) -> ImprovementProposal | None:
        record = await self.session.get(ImprovementProposalRecord, proposal_id)
        return self._improvement_proposal_from_record(record) if record is not None else None

    async def approve_improvement_proposal(self, proposal_id: UUID) -> ImprovementProposal:
        record = await self.session.get(ImprovementProposalRecord, proposal_id)
        if record is None:
            raise KeyError(f"improvement proposal not found: {proposal_id}")
        record.status = ImprovementProposalStatus.APPROVED.value
        record.rejection_reason = None
        record.approved_at = datetime.now(UTC)
        if not record.proof_spec:
            state = await self.get_run(record.run_id)
            diagnosis = state.get("diagnosis", {}) if isinstance(state, dict) else {}
            record.proof_spec = proof_spec_for_proposal(
                baseline_run_id=record.source_run_id,
                playbook_key=state.get("playbook_key") if isinstance(state, dict) else None,
                target_component=record.target_component,
                failure_signature=record.failure_signature,
                root_cause=diagnosis.get("root_cause") if isinstance(diagnosis, dict) else None,
                success_check=record.success_check,
            )
        await self._persist()
        await self.session.refresh(record)
        return self._improvement_proposal_from_record(record)

    async def reject_improvement_proposal(self, proposal_id: UUID, reason: str) -> ImprovementProposal:
        record = await self.session.get(ImprovementProposalRecord, proposal_id)
        if record is None:
            raise KeyError(f"improvement proposal not found: {proposal_id}")
        record.status = ImprovementProposalStatus.REJECTED.value
        record.rejection_reason = reason
        await self._persist()
        await self.session.refresh(record)
        return self._improvement_proposal_from_record(record)

    async def mark_improvement_proposal_implemented(self, proposal_id: UUID) -> ImprovementProposal:
        return await self.implement_improvement_proposal(proposal_id, {})

    async def implement_improvement_proposal(self, proposal_id: UUID, implementation_result: dict[str, Any]) -> ImprovementProposal:
        record = await self.session.get(ImprovementProposalRecord, proposal_id)
        if record is None:
            raise KeyError(f"improvement proposal not found: {proposal_id}")
        if record.status != ImprovementProposalStatus.APPROVED.value:
            raise ValueError(f"proposal must be approved before implementation: status={record.status}")
        record.status = ImprovementProposalStatus.IMPLEMENTED.value
        record.implemented_at = datetime.now(UTC)
        record.implementation_result = implementation_result
        await self._persist()
        await self.session.refresh(record)
        return self._improvement_proposal_from_record(record)

    async def mark_improvement_proposal_proven(self, proposal_id: UUID) -> ImprovementProposal:
        record = await self.session.get(ImprovementProposalRecord, proposal_id)
        if record is None:
            raise KeyError(f"improvement proposal not found: {proposal_id}")
        if record.status == ImprovementProposalStatus.PROVEN.value:
            await self._resolve_matching_failure_learning(record)
            await self._persist()
            await self.session.refresh(record)
            return self._improvement_proposal_from_record(record)
        if record.status != ImprovementProposalStatus.IMPLEMENTED.value:
            raise ValueError(f"proposal must be implemented before proof can mark it proven: status={record.status}")
        record.status = ImprovementProposalStatus.PROVEN.value
        record.proven_at = datetime.now(UTC)
        await self._resolve_matching_failure_learning(record)
        await self._persist()
        await self.session.refresh(record)
        return self._improvement_proposal_from_record(record)

    async def _resolve_matching_failure_learning(self, proposal: ImprovementProposalRecord) -> None:
        learning = (
            await self.session.execute(
                select(FailureLearningRecord).where(
                    FailureLearningRecord.failure_signature == proposal.failure_signature,
                    FailureLearningRecord.target_component == proposal.target_component,
                )
            )
        ).scalar_one_or_none()
        if learning is not None:
            learning.status = FailureLearningStatus.RESOLVED.value

    async def record_failure_learnings(self, learnings: list[FailureLearning]) -> list[FailureLearning]:
        recorded: list[FailureLearning] = []
        for learning in learnings:
            record = (
                await self.session.execute(
                    select(FailureLearningRecord).where(
                        FailureLearningRecord.failure_signature == learning.failure_signature,
                        FailureLearningRecord.target_component == learning.target_component,
                    )
                )
            ).scalar_one_or_none()
            if record is None:
                record = FailureLearningRecord(
                    id=learning.id,
                    failure_signature=learning.failure_signature,
                    target_component=learning.target_component,
                    root_cause=learning.root_cause,
                    playbook_key=learning.playbook_key,
                    proposal_type=learning.proposal_type,
                    learning_summary=learning.learning_summary,
                    proposed_next_step=learning.proposed_next_step,
                    risk=learning.risk,
                    success_check=learning.success_check,
                    severity=learning.severity,
                    occurrence_count=learning.occurrence_count,
                    first_seen_run_id=learning.first_seen_run_id,
                    last_seen_run_id=learning.last_seen_run_id,
                    evidence_refs={"items": learning.evidence_refs},
                    run_ids={"items": learning.run_ids},
                    status=learning.status.value,
                    created_at=datetime.now(UTC),
                )
                self.session.add(record)
            else:
                run_ids = self._json_items(record.run_ids)
                if learning.last_seen_run_id not in run_ids:
                    run_ids.append(learning.last_seen_run_id)
                    record.occurrence_count += 1
                record.root_cause = learning.root_cause
                record.playbook_key = learning.playbook_key
                record.proposal_type = learning.proposal_type
                record.learning_summary = learning.learning_summary
                record.proposed_next_step = learning.proposed_next_step
                record.risk = learning.risk
                record.success_check = learning.success_check
                record.severity = self._max_severity(record.severity, learning.severity)
                record.last_seen_run_id = learning.last_seen_run_id
                evidence_refs = (self._json_items(record.evidence_refs) + learning.evidence_refs)[-30:]
                record.evidence_refs = {"items": evidence_refs}
                record.run_ids = {"items": run_ids[-50:]}
                record.status = FailureLearningStatus.ACTIVE.value
            await self._persist()
            await self.session.refresh(record)
            recorded.append(self._failure_learning_from_record(record))
        return recorded

    async def list_failure_learnings(
        self,
        status: FailureLearningStatus | None = None,
        playbook_key: str | None = None,
    ) -> list[FailureLearning]:
        statement = select(FailureLearningRecord).order_by(desc(FailureLearningRecord.occurrence_count), desc(FailureLearningRecord.updated_at))
        if status is not None:
            statement = statement.where(FailureLearningRecord.status == status.value)
        if playbook_key is not None:
            statement = statement.where(FailureLearningRecord.playbook_key == playbook_key)
        records = (await self.session.execute(statement)).scalars().all()
        return [self._failure_learning_from_record(record) for record in records]

    async def has_open_improvement_proposal(self, failure_signature: str, target_component: str) -> bool:
        open_statuses = {
            ImprovementProposalStatus.PROPOSED.value,
            ImprovementProposalStatus.APPROVED.value,
            ImprovementProposalStatus.IMPLEMENTED.value,
        }
        record = (
            await self.session.execute(
                select(ImprovementProposalRecord).where(
                    ImprovementProposalRecord.failure_signature == failure_signature,
                    ImprovementProposalRecord.target_component == target_component,
                    ImprovementProposalRecord.status.in_(open_statuses),
                )
            )
        ).scalar_one_or_none()
        return record is not None

    async def list_recent_runs(self, limit: int = 50, playbook_key: str | None = None) -> list[dict[str, Any]]:
        statement = select(ProcessRunRecord.id).order_by(desc(ProcessRunRecord.updated_at)).limit(limit)
        if playbook_key is not None:
            statement = statement.where(ProcessRunRecord.playbook_key == playbook_key)
        run_ids = (await self.session.execute(statement)).scalars().all()
        runs: list[dict[str, Any]] = []
        for run_id in run_ids:
            run = await self.get_run(run_id)
            if run is not None:
                runs.append(run)
        return runs

    async def add_system_review(self, review: SystemReview) -> SystemReview:
        record = SystemReviewRecord(
            id=review.id,
            scope=review.scope,
            playbook_key=review.playbook_key,
            run_count=review.run_count,
            learning_count=review.learning_count,
            payload=review.model_dump(mode="json"),
            created_at=datetime.now(UTC),
        )
        self.session.add(record)
        await self._persist()
        await self.session.refresh(record)
        return self._system_review_from_record(record)

    async def list_system_reviews(self, playbook_key: str | None = None) -> list[SystemReview]:
        statement = select(SystemReviewRecord).order_by(desc(SystemReviewRecord.created_at))
        if playbook_key is not None:
            statement = statement.where(SystemReviewRecord.playbook_key == playbook_key)
        records = (await self.session.execute(statement)).scalars().all()
        return [self._system_review_from_record(record) for record in records]

    async def upsert_registry_item(self, item: RegistryItem) -> RegistryItem:
        record = await self._get_registry_item_record(item.kind, item.key)
        if record is None:
            record = RegistryItemRecord(
                id=item.id,
                kind=item.kind.value,
                key=item.key,
                version=item.version,
                status=item.status,
                spec=item.spec,
                metadata_=item.metadata,
            )
            self.session.add(record)
        else:
            record.version = item.version
            record.status = item.status
            record.spec = item.spec
            record.metadata_ = item.metadata
        await self._persist()
        await self.session.refresh(record)
        return self._registry_item_from_record(record)

    async def list_registry_items(self, kind: RegistryKind) -> list[RegistryItem]:
        records = (
            await self.session.execute(select(RegistryItemRecord).where(RegistryItemRecord.kind == kind.value).order_by(RegistryItemRecord.key))
        ).scalars().all()
        return [self._registry_item_from_record(record) for record in records]

    async def get_registry_item(self, kind: RegistryKind, key: str) -> RegistryItem | None:
        record = await self._get_registry_item_record(kind, key)
        return self._registry_item_from_record(record) if record else None

    async def create_registry_change_candidate(self, candidate: RegistryChangeCandidateCreate) -> RegistryChangeCandidate:
        status = RegistryChangeStatus.AUTO_APPLIED_SAFE if is_safe_registry_change(candidate) else RegistryChangeStatus.PROPOSED
        record = RegistryChangeCandidateRecord(
            kind=candidate.kind.value,
            key=candidate.key,
            change_type=candidate.change_type,
            status=status.value,
            payload=candidate.payload,
            reason=candidate.reason,
        )
        self.session.add(record)
        await self._persist()
        if status == RegistryChangeStatus.AUTO_APPLIED_SAFE:
            await self._apply_candidate(candidate)
        return self._registry_candidate_from_record(record)

    async def approve_registry_change_candidate(self, candidate_id: UUID) -> RegistryChangeCandidate:
        record = await self.session.get(RegistryChangeCandidateRecord, candidate_id)
        if record is None:
            raise KeyError(f"registry change candidate not found: {candidate_id}")
        candidate = RegistryChangeCandidateCreate(
            kind=RegistryKind(record.kind),
            key=record.key,
            change_type=record.change_type,
            payload=record.payload,
            reason=record.reason,
        )
        await self._apply_candidate(candidate)
        record.status = RegistryChangeStatus.APPROVED.value
        await self._persist()
        return self._registry_candidate_from_record(record)

    async def reject_registry_change_candidate(self, candidate_id: UUID) -> RegistryChangeCandidate:
        record = await self.session.get(RegistryChangeCandidateRecord, candidate_id)
        if record is None:
            raise KeyError(f"registry change candidate not found: {candidate_id}")
        record.status = RegistryChangeStatus.REJECTED.value
        await self._persist()
        return self._registry_candidate_from_record(record)

    async def _apply_candidate(self, candidate: RegistryChangeCandidateCreate) -> RegistryItem:
        item = await self.get_registry_item(candidate.kind, candidate.key)
        updated = apply_registry_change(item, candidate)
        return await self.upsert_registry_item(updated)

    async def _get_registry_item_record(self, kind: RegistryKind, key: str) -> RegistryItemRecord | None:
        return (
            await self.session.execute(select(RegistryItemRecord).where(RegistryItemRecord.kind == kind.value, RegistryItemRecord.key == key))
        ).scalar_one_or_none()

    @staticmethod
    def _registry_item_from_record(record: RegistryItemRecord) -> RegistryItem:
        return RegistryItem(
            id=record.id,
            kind=RegistryKind(record.kind),
            key=record.key,
            version=record.version,
            status=record.status,
            spec=record.spec,
            metadata=record.metadata_,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _registry_candidate_from_record(record: RegistryChangeCandidateRecord) -> RegistryChangeCandidate:
        return RegistryChangeCandidate(
            id=record.id,
            kind=RegistryKind(record.kind),
            key=record.key,
            change_type=record.change_type,
            payload=record.payload,
            reason=record.reason,
            status=RegistryChangeStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _improvement_proposal_from_record(record: ImprovementProposalRecord) -> ImprovementProposal:
        evidence = record.evidence.get("items", []) if isinstance(record.evidence, dict) else []
        return ImprovementProposal(
            id=record.id,
            run_id=record.run_id,
            source_run_id=record.source_run_id,
            proposal_type=record.proposal_type,
            target_component=record.target_component,
            failure_signature=record.failure_signature,
            problem=record.problem,
            proposed_change=record.proposed_change,
            risk=record.risk,
            success_check=record.success_check,
            evidence=evidence,
            behavior_change_requires_approval=record.behavior_change_requires_approval,
            proof_spec=record.proof_spec,
            implementation_result=record.implementation_result or {},
            status=ImprovementProposalStatus(record.status),
            rejection_reason=record.rejection_reason,
            approved_at=record.approved_at,
            implemented_at=record.implemented_at,
            proven_at=record.proven_at,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _failure_learning_from_record(record: FailureLearningRecord) -> FailureLearning:
        return FailureLearning(
            id=record.id,
            failure_signature=record.failure_signature,
            target_component=record.target_component,
            root_cause=record.root_cause,
            playbook_key=record.playbook_key,
            proposal_type=record.proposal_type,
            learning_summary=record.learning_summary,
            proposed_next_step=record.proposed_next_step,
            risk=record.risk,
            success_check=record.success_check,
            severity=record.severity,
            occurrence_count=record.occurrence_count,
            first_seen_run_id=record.first_seen_run_id,
            last_seen_run_id=record.last_seen_run_id,
            evidence_refs=WorkingMemoryStore._json_items(record.evidence_refs),
            run_ids=WorkingMemoryStore._json_items(record.run_ids),
            status=FailureLearningStatus(record.status),
            created_at=record.created_at,
            updated_at=record.updated_at,
        )

    @staticmethod
    def _system_review_from_record(record: SystemReviewRecord) -> SystemReview:
        payload = record.payload if isinstance(record.payload, dict) else {}
        return SystemReview(
            id=record.id,
            scope=record.scope,
            playbook_key=record.playbook_key,
            run_count=record.run_count,
            learning_count=record.learning_count,
            findings=payload.get("findings", []),
            recommendations=payload.get("recommendations", []),
            created_proposal_ids=payload.get("created_proposal_ids", []),
            worker_execution=payload.get("worker_execution", {}),
            created_at=record.created_at,
        )

    @staticmethod
    def _json_items(payload: dict[str, Any] | None) -> list[Any]:
        if not isinstance(payload, dict):
            return []
        items = payload.get("items", [])
        return items if isinstance(items, list) else []

    @staticmethod
    def _max_severity(current: str, incoming: str) -> str:
        order = {"low": 0, "medium": 1, "high": 2}
        return incoming if order.get(incoming, 0) > order.get(current, 0) else current
