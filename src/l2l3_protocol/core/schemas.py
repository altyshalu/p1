from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class RunStatus(StrEnum):
    CREATED = "created"
    RUNNING = "running"
    WAITING_APPROVAL = "waiting_approval"
    WAITING_USER = "waiting_user"
    PAUSED = "paused"
    CANCELLED = "cancelled"
    COMPLETED = "completed"
    FAILED = "failed"


class RunMode(StrEnum):
    EXECUTION = "execution"
    DESIGN = "design"


class TaskStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    NEEDS_REPAIR = "needs_repair"
    WAITING_APPROVAL = "waiting_approval"


class ArtifactType(StrEnum):
    SIGNALS = "signals"
    CONTENT_ATOMS = "content_atoms"
    CHANNEL_DRAFTS = "channel_drafts"
    EVAL_REPORT = "eval_report"
    APPROVAL_DECISION = "approval_decision"
    MEMORY_CANDIDATES = "memory_candidates"
    REGISTRY_CHANGE_CANDIDATE = "registry_change_candidate"
    PLAYBOOK_PROPOSAL = "playbook_proposal"
    RUN_DIAGNOSIS = "run_diagnosis"
    DESIGN_REPORT = "design_report"
    GENERIC = "generic"


class MemoryLayer(StrEnum):
    WORKING = "working"
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class RegistryKind(StrEnum):
    TOOL = "tool"
    WORKER = "worker"
    EVAL = "eval"
    PLAYBOOK = "playbook"
    FAILURE_PATTERN = "failure_pattern"


class RegistryChangeStatus(StrEnum):
    PROPOSED = "proposed"
    AUTO_APPLIED_SAFE = "auto_applied_safe"
    APPROVED = "approved"
    REJECTED = "rejected"
    SUPERSEDED = "superseded"


class ImprovementProposalStatus(StrEnum):
    PROPOSED = "proposed"
    APPROVED = "approved"
    REJECTED = "rejected"


class ProcessRunCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    goal: str
    playbook_key: str = "build-in-public"
    l2_mode: RunMode = RunMode.EXECUTION
    inputs: dict[str, Any] = Field(default_factory=dict)
    require_human_approval: bool = True


class RunMessageCreate(BaseModel):
    message: str


class RunControlCreate(BaseModel):
    action: str
    payload: dict[str, Any] = Field(default_factory=dict)


class ProcessRun(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    playbook_key: str
    l2_mode: RunMode = RunMode.EXECUTION
    goal: str
    status: RunStatus = RunStatus.CREATED
    input: dict[str, Any] = Field(default_factory=dict)
    output: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class WorkOrder(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    task_type: str
    goal: str
    worker_profile: str
    worker_type: str = "sandboxed_subprocess"
    inputs: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    allowed_tools: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    stop_conditions: list[str] = Field(default_factory=list)
    grader_spec: dict[str, Any] = Field(default_factory=dict)
    retry_policy: dict[str, Any] = Field(default_factory=dict)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    external_action_policy: dict[str, Any] = Field(default_factory=dict)
    status: TaskStatus = TaskStatus.PENDING


class L2SpawnWorkOrder(BaseModel):
    task_type: str
    worker_profile: str
    goal: str
    inputs: dict[str, Any] = Field(default_factory=dict)
    artifact_type: str = ArtifactType.GENERIC.value
    allowed_tools: list[str] = Field(default_factory=list)


class L2SupervisorAction(BaseModel):
    action: str
    message: str | None = None
    tasks: list[L2SpawnWorkOrder] = Field(default_factory=list)
    output: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    registry_change_candidate: dict[str, Any] | None = None
    playbook_proposal: dict[str, Any] | None = None


class L2DesignProposal(BaseModel):
    playbook_key: str
    playbook_spec: dict[str, Any]
    required_workers: list[dict[str, Any]] = Field(default_factory=list)
    required_tools: list[dict[str, Any]] = Field(default_factory=list)
    required_evals: list[dict[str, Any]] = Field(default_factory=list)
    registry_change_candidates: list[dict[str, Any]] = Field(default_factory=list)
    test_plan: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    approval_required: bool = True


class Artifact(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    task_id: UUID | None = None
    artifact_type: ArtifactType
    payload: dict[str, Any]


class EvalResult(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    task_id: UUID | None = None
    passed: bool
    score: float
    reasons: list[str] = Field(default_factory=list)
    checks: dict[str, Any] = Field(default_factory=dict)
    eval_key: str | None = None
    eval_type: str | None = None
    threshold: float | None = None


class MemoryWrite(BaseModel):
    layer: MemoryLayer
    run_id: UUID
    task_id: UUID | None = None
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RegistryItem(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: RegistryKind
    key: str
    version: str = "0.1.0"
    status: str = "active"
    spec: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None


class RegistryChangeCandidateCreate(BaseModel):
    kind: RegistryKind
    key: str
    change_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None


class RegistryChangeCandidate(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    kind: RegistryKind
    key: str
    change_type: str
    payload: dict[str, Any] = Field(default_factory=dict)
    reason: str | None = None
    status: RegistryChangeStatus = RegistryChangeStatus.PROPOSED
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ImprovementProposal(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    run_id: UUID
    source_run_id: str
    proposal_type: str
    target_component: str = "unknown"
    failure_signature: str = "unknown"
    problem: str
    proposed_change: str
    risk: str
    success_check: str
    evidence: list[dict[str, Any]] = Field(default_factory=list)
    status: ImprovementProposalStatus = ImprovementProposalStatus.PROPOSED
    rejection_reason: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
