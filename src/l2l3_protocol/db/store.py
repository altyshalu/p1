from typing import Any
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from l2l3_protocol.core.schemas import (
    Artifact,
    EvalResult,
    ImprovementProposal,
    ImprovementProposalStatus,
    ProcessRun,
    RegistryChangeCandidate,
    RegistryChangeCandidateCreate,
    RegistryChangeStatus,
    RegistryItem,
    RegistryKind,
    RunStatus,
    TaskStatus,
    WorkOrder,
)
from l2l3_protocol.db.models import (
    ArtifactRecord,
    EvalResultRecord,
    EventRecord,
    ImprovementProposalRecord,
    ProcessRunRecord,
    RegistryChangeCandidateRecord,
    RegistryItemRecord,
    WorkOrderRecord,
)
from l2l3_protocol.hub.registry import apply_registry_change, is_safe_registry_change


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
            problem=proposal.problem,
            proposed_change=proposal.proposed_change,
            risk=proposal.risk,
            success_check=proposal.success_check,
            evidence={"items": proposal.evidence},
            status=proposal.status.value,
            rejection_reason=proposal.rejection_reason,
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

    async def approve_improvement_proposal(self, proposal_id: UUID) -> ImprovementProposal:
        record = await self.session.get(ImprovementProposalRecord, proposal_id)
        if record is None:
            raise KeyError(f"improvement proposal not found: {proposal_id}")
        record.status = ImprovementProposalStatus.APPROVED.value
        record.rejection_reason = None
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
            problem=record.problem,
            proposed_change=record.proposed_change,
            risk=record.risk,
            success_check=record.success_check,
            evidence=evidence,
            status=ImprovementProposalStatus(record.status),
            rejection_reason=record.rejection_reason,
            created_at=record.created_at,
            updated_at=record.updated_at,
        )
