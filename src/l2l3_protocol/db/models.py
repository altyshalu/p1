from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    type_annotation_map = {dict[str, Any]: JSONB}


class ProcessRunRecord(Base):
    __tablename__ = "process_runs"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    process_key: Mapped[str] = mapped_column(String(100), index=True)
    goal: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String(40), index=True)
    input: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    output: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    tasks: Mapped[list["TaskContractRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    artifacts: Mapped[list["ArtifactRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    evals: Mapped[list["EvalResultRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")
    events: Mapped[list["EventRecord"]] = relationship(back_populates="run", cascade="all, delete-orphan")


class TaskContractRecord(Base):
    __tablename__ = "task_contracts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_type: Mapped[str] = mapped_column(String(100), index=True)
    worker_profile: Mapped[str] = mapped_column(String(100), index=True)
    status: Mapped[str] = mapped_column(String(40), index=True)
    goal: Mapped[str] = mapped_column(String)
    contract: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    run: Mapped[ProcessRunRecord] = relationship(back_populates="tasks")


class ArtifactRecord(Base):
    __tablename__ = "artifacts"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("task_contracts.id"), nullable=True, index=True)
    artifact_type: Mapped[str] = mapped_column(String(80), index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ProcessRunRecord] = relationship(back_populates="artifacts")


class EvalResultRecord(Base):
    __tablename__ = "eval_results"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("task_contracts.id"), nullable=True, index=True)
    passed: Mapped[bool]
    score: Mapped[float]
    payload: Mapped[dict[str, Any]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    run: Mapped[ProcessRunRecord] = relationship(back_populates="evals")


class EventRecord(Base):
    __tablename__ = "events"

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    run_id: Mapped[UUID] = mapped_column(ForeignKey("process_runs.id"), index=True)
    task_id: Mapped[UUID | None] = mapped_column(ForeignKey("task_contracts.id"), nullable=True, index=True)
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
