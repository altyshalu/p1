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
    GOAL_HYPOTHESES = "goal_hypotheses"
    GOAL_BRIEF = "goal_brief"
    EVAL_REPORT = "eval_report"
    APPROVAL_DECISION = "approval_decision"
    MEMORY_CANDIDATES = "memory_candidates"
    REGISTRY_CHANGE_CANDIDATE = "registry_change_candidate"
    PLAYBOOK_PROPOSAL = "playbook_proposal"
    RUN_DIAGNOSIS = "run_diagnosis"
    SYSTEM_REVIEW = "system_review"
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
    IMPLEMENTED = "implemented"
    PROVEN = "proven"
    STALE = "stale"


class FailureLearningStatus(StrEnum):
    ACTIVE = "active"
    RESOLVED = "resolved"
    STALE = "stale"


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


class UserChoiceOption(BaseModel):
    id: str
    label: str
    description: str


class UserInteractionContract(BaseModel):
    kind: str
    question: str
    options: list[UserChoiceOption] = Field(default_factory=list)
    why_this_question: str | None = None
    resolution_hint: str | None = None


class L2SupervisorAction(BaseModel):
    action: str
    message: str | None = None
    interaction: UserInteractionContract | None = None
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
    behavior_change_requires_approval: bool = True
    proof_spec: dict[str, Any] = Field(default_factory=dict)
    implementation_result: dict[str, Any] = Field(default_factory=dict)
    status: ImprovementProposalStatus = ImprovementProposalStatus.PROPOSED
    rejection_reason: str | None = None
    approved_at: datetime | None = None
    implemented_at: datetime | None = None
    proven_at: datetime | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class FailureLearning(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    failure_signature: str
    target_component: str
    root_cause: str
    playbook_key: str | None = None
    proposal_type: str
    learning_summary: str
    proposed_next_step: str
    risk: str
    success_check: str
    severity: str = "medium"
    occurrence_count: int = 1
    first_seen_run_id: str
    last_seen_run_id: str
    worker_family: str | None = None
    eval_family: str | None = None
    tool_family: str | None = None
    repair_attempt_count: int = 0
    human_intervention_count: int = 0
    evidence_refs: list[dict[str, Any]] = Field(default_factory=list)
    run_ids: list[str] = Field(default_factory=list)
    status: FailureLearningStatus = FailureLearningStatus.ACTIVE
    created_at: datetime | None = None
    updated_at: datetime | None = None


class SystemReview(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    scope: str = "recent_runs"
    playbook_key: str | None = None
    run_count: int = 0
    learning_count: int = 0
    findings: list[dict[str, Any]] = Field(default_factory=list)
    recommendations: list[dict[str, Any]] = Field(default_factory=list)
    weak_components: list[dict[str, Any]] = Field(default_factory=list)
    excess_repairs: list[dict[str, Any]] = Field(default_factory=list)
    human_interruptions: list[dict[str, Any]] = Field(default_factory=list)
    needed_changes: list[dict[str, Any]] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    created_proposal_ids: list[str] = Field(default_factory=list)
    worker_execution: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None


class RecentSystemReviewCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    limit: int = Field(default=50, ge=1, le=250)
    playbook_key: str | None = None
    since_hours: int | None = Field(default=None, ge=1, le=24 * 30)


class RegressionCase(BaseModel):
    id: UUID = Field(default_factory=uuid4)
    proposal_id: UUID
    baseline_run_id: str
    failure_signature: str
    target_component: str
    comparable_run_input: dict[str, Any] = Field(default_factory=dict)
    proof_command: str
    expected_absent_failure: str
    last_after_run_id: str | None = None
    last_proof_status: str = "pending"
    last_proof_result: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
