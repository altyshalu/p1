from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB}


class ProcessRunRecord(Base):
    __tablename__ = "process_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    playbook_key: Mapped[str] = mapped_column(String(100), index=True)
    l2_mode: Mapped[str] = mapped_column(String(40), index=True)
    goal: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(40), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    work_orders: Mapped[list["WorkOrderRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    artifacts: Mapped[list["ArtifactRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    evals: Mapped[list["EvalResultRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    events: Mapped[list["EventRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class WorkOrderRecord(Base):
    __tablename__ = "work_orders"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), index=True)
    worker_profile: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    goal: Mapped[str] = mapped_column(String)
    work_order: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    run: Mapped[ProcessRunRecord] = relationship(back_populates="work_orders")


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ProcessRunRecord] = relationship(back_populates="artifacts")


class EvalResultRecord(Base):
    __tablename__ = "eval_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True, index=True)
    passed: Mapped[bool]
    score: Mapped[float]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ProcessRunRecord] = relationship(back_populates="evals")


class EventRecord(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("work_orders.id"), nullable=True, index=True)
    event_type: Mapped[str] = mapped_column(String(100), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ProcessRunRecord] = relationship(back_populates="events")


class RegistryItemRecord(Base):
    __tablename__ = "registry_items"
    __table_args__ = (UniqueConstraint("kind", "key", name="uq_registry_items_kind_key"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    version: Mapped[str] = mapped_column(String(40), default="0.1.0")
    status: Mapped[str] = mapped_column(String(40), default="active", index=True)
    spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    metadata_: Mapped[dict[str, Any]] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class RegistryChangeCandidateRecord(Base):
    __tablename__ = "registry_change_candidates"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    kind: Mapped[str] = mapped_column(String(40), index=True)
    key: Mapped[str] = mapped_column(String(120), index=True)
    change_type: Mapped[str] = mapped_column(String(80), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    reason: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class ImprovementProposalRecord(Base):
    __tablename__ = "improvement_proposals"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    source_run_id: Mapped[str] = mapped_column(String(80), index=True)
    proposal_type: Mapped[str] = mapped_column(String(80), index=True)
    target_component: Mapped[str] = mapped_column(String(160), default="unknown", index=True)
    failure_signature: Mapped[str] = mapped_column(String(160), default="unknown", index=True)
    problem: Mapped[str] = mapped_column(String)
    proposed_change: Mapped[str] = mapped_column(String)
    risk: Mapped[str] = mapped_column(String)
    success_check: Mapped[str] = mapped_column(String)
    evidence: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    behavior_change_requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    proof_spec: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    implementation_result: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(40), index=True)
    rejection_reason: Mapped[str | None] = mapped_column(String, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    implemented_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    proven_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class FailureLearningRecord(Base):
    __tablename__ = "failure_learnings"
    __table_args__ = (UniqueConstraint("failure_signature", "target_component", name="uq_failure_learnings_signature_target"),)

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    failure_signature: Mapped[str] = mapped_column(String(160), index=True)
    target_component: Mapped[str] = mapped_column(String(160), index=True)
    root_cause: Mapped[str] = mapped_column(String(120), index=True)
    playbook_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    proposal_type: Mapped[str] = mapped_column(String(80), index=True)
    learning_summary: Mapped[str] = mapped_column(String)
    proposed_next_step: Mapped[str] = mapped_column(String)
    risk: Mapped[str] = mapped_column(String)
    success_check: Mapped[str] = mapped_column(String)
    severity: Mapped[str] = mapped_column(String(40), index=True)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)
    first_seen_run_id: Mapped[str] = mapped_column(String(80))
    last_seen_run_id: Mapped[str] = mapped_column(String(80), index=True)
    evidence_refs: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    run_ids: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    status: Mapped[str] = mapped_column(String(40), index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class SystemReviewRecord(Base):
    __tablename__ = "system_reviews"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    scope: Mapped[str] = mapped_column(String(80), index=True)
    playbook_key: Mapped[str | None] = mapped_column(String(100), nullable=True, index=True)
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    learning_count: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
