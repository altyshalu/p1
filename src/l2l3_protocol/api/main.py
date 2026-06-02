from collections.abc import AsyncIterator
import asyncio
from datetime import UTC, datetime, timedelta
from contextlib import asynccontextmanager
import json
from time import perf_counter
from typing import Any
from uuid import UUID
from uuid import uuid4

import structlog
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
from sqlalchemy.ext.asyncio import AsyncSession

from l2l3_protocol.api.state import app_state, build_memory_router
from l2l3_protocol.config import get_settings
from l2l3_protocol.core.schemas import (
    FailureLearningStatus,
    ImprovementProposal,
    ImprovementProposalStatus,
    ProcessRun,
    ProcessRunCreate,
    RecentSystemReviewCreate,
    RegistryChangeCandidateCreate,
    RegistryKind,
    RunControlCreate,
    RunMessageCreate,
    RunStatus,
    SystemReview,
    WorkOrder,
)
from l2l3_protocol.core.terminology import normalize_hub_kind
from l2l3_protocol.db.migrations import run_upgrade_head
from l2l3_protocol.db.session import get_session, make_engine, make_session_factory
from l2l3_protocol.db.store import WorkingMemoryStore
from l2l3_protocol.hub.registry import yaml_registry_items
from l2l3_protocol.logging import configure_logging, get_logger
from l2l3_protocol.memory.adapters import ProceduralRegistry
from l2l3_protocol.runtime.diagnostics import analyze_run
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.l3_executor import L3SandboxExecutor, L3WorkerExecutionError
from l2l3_protocol.runtime.process_runtime import ProcessRuntime
from l2l3_protocol.runtime.self_improvement import (
    build_failure_learnings,
    build_system_learning_report,
    proposal_from_failure_learning,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging(settings.log_dir, settings.log_level)
    await asyncio.to_thread(run_upgrade_head, settings)
    engine = make_engine(settings)
    session_factory = make_session_factory(engine)
    app_state.settings = settings
    app_state.engine = engine
    app_state.session_factory = session_factory
    app_state.memory_router = build_memory_router(settings)
    app_state.registry = ProceduralRegistry(settings.procedural_registry_path)
    app_state.hermes = HermesRuntime(settings)
    get_logger().info("app_started", environment=settings.environment)
    yield
    await engine.dispose()


app = FastAPI(title="L2-L3 Active Inference Runtime", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def request_logging(request: Request, call_next) -> Response:
    request_id = request.headers.get("x-request-id") or str(id(request))
    structlog.contextvars.clear_contextvars()
    structlog.contextvars.bind_contextvars(request_id=request_id, path=request.url.path, method=request.method)
    start = perf_counter()
    try:
        response = await call_next(request)
        get_logger("protocol.events").info(
            "api_request_completed",
            status=response.status_code,
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )
        response.headers["x-request-id"] = request_id
        return response
    except Exception as exc:
        get_logger("protocol.events").exception(
            "api_request_failed",
            error_type=type(exc).__name__,
            duration_ms=round((perf_counter() - start) * 1000, 2),
        )
        raise


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "service": "l2l3-protocol"}


@app.get("/runtime/capabilities")
async def runtime_capabilities() -> dict[str, Any]:
    settings = app_state.settings
    return {
        'hermes': {
            'enabled': settings.hermes_enabled,
            'configured': bool(settings.deepseek_api_key),
            'available': app_state.hermes.available(),
            'model': settings.hermes_model,
            'max_iterations': settings.hermes_max_iterations,
        },
        'memory': {
            'agentmemory_enabled': settings.agentmemory_enabled,
            'mem0_enabled': settings.mem0_enabled,
            'mem0_vector_provider': settings.mem0_vector_provider,
        },
    }


@app.get("/runs")
async def list_runs(
    playbook_key: str | None = None,
    limit: int = 20,
    since_hours: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    bounded_limit = max(1, min(limit, 100))
    return await WorkingMemoryStore(session).list_recent_runs(limit=bounded_limit, playbook_key=playbook_key, since_hours=since_hours)


def _build_run_summary(run: dict[str, Any]) -> dict[str, Any]:
    artifacts = run.get("artifacts", []) if isinstance(run.get("artifacts"), list) else []
    tasks = run.get("tasks", []) if isinstance(run.get("tasks"), list) else []
    evals = run.get("evals", []) if isinstance(run.get("evals"), list) else []
    artifact_counts: dict[str, int] = {}
    for artifact in artifacts:
        artifact_type = str(artifact.get("artifact_type") or "unknown")
        artifact_counts[artifact_type] = artifact_counts.get(artifact_type, 0) + 1
    task_status_counts: dict[str, int] = {}
    for task in tasks:
        status = str(task.get("status") or "unknown")
        task_status_counts[status] = task_status_counts.get(status, 0) + 1
    output = run.get("output", {}) if isinstance(run.get("output"), dict) else {}
    latest_approval_preview = next(
        (item.get("payload", {}) for item in reversed(artifacts) if item.get("artifact_type") == "p1_external_action_preview"),
        output.get("approval_preview", {}),
    )
    latest_eval_results: dict[str, Any] = {}
    for item in evals:
        eval_key = str(item.get("eval_key") or item.get("id") or "latest")
        latest_eval_results[eval_key] = item
    pending_actions: list[dict[str, Any]] = []
    if run.get("status") == RunStatus.WAITING_APPROVAL.value:
        pending_actions.append({"type": "approval", "summary": "Run is waiting for human approval before external actions."})
    if run.get("status") == RunStatus.WAITING_USER.value:
        pending_actions.append({"type": "user_input", "summary": "Run is waiting for user input."})
    return {
        "id": run.get("id"),
        "status": run.get("status"),
        "playbook_key": run.get("playbook_key"),
        "goal": run.get("goal"),
        "latest_metrics": output.get("metrics", {}),
        "latest_diagnosis": run.get("diagnosis"),
        "latest_approval_preview": latest_approval_preview,
        "external_sync_status": {
            "google_sheets": output.get("external_sync_result"),
            "outreach_master": output.get("outreach_master_sync_result"),
            "requested": {
                "google_sheets": bool(output.get("external_sync_requested")),
                "outreach_master": bool(output.get("outreach_master_sync_requested")),
            },
        },
        "artifact_counts": artifact_counts,
        "task_status_counts": task_status_counts,
        "latest_eval_results": latest_eval_results,
        "pending_actions": pending_actions,
    }


def make_runtime(store: WorkingMemoryStore) -> ProcessRuntime:
    return ProcessRuntime(
        store=store,
        registry=app_state.registry,
        memory=app_state.memory_router,
        hermes=app_state.hermes,
    )


@app.post("/runs")
async def create_run(payload: ProcessRunCreate, background_tasks: BackgroundTasks, session: AsyncSession = Depends(get_session)) -> dict:
    store = WorkingMemoryStore(session)
    run = ProcessRun(playbook_key=payload.playbook_key, l2_mode=payload.l2_mode, goal=payload.goal, input=payload.model_dump(mode="json"))
    await store.create_run(run)
    await session.commit()
    background_tasks.add_task(execute_run, run.id)
    return {"id": str(run.id), "status": run.status.value, "playbook_key": run.playbook_key, "l2_mode": run.l2_mode.value, "goal": run.goal}


async def execute_run(run_id: UUID) -> None:
    async with app_state.session_factory() as session:
        store = WorkingMemoryStore(session, auto_commit=True)
        try:
            await make_runtime(store).run_until_blocked_or_done(run_id)
        except Exception as exc:
            await store.set_run_status(run_id, RunStatus.FAILED, output={"error_type": type(exc).__name__, "error": str(exc)})
            await store.add_event(run_id, "run_failed", {"error_type": type(exc).__name__, "error": str(exc)})
            failed_state = await store.get_run(run_id)
            if failed_state is not None and failed_state.get("diagnosis") is None:
                diagnosis, proposals = analyze_run(failed_state)
                await store.add_artifact(diagnosis)
                await store.add_event(run_id, "run_diagnosis_created", diagnosis.payload)
                for proposal in proposals:
                    await store.add_improvement_proposal(proposal)
                    await store.add_event(run_id, "improvement_proposal_created", proposal.model_dump(mode="json"))
                learnings = await store.record_failure_learnings(build_failure_learnings(failed_state, diagnosis.payload, proposals))
                for learning in learnings:
                    await store.add_event(run_id, "failure_learning_recorded", learning.model_dump(mode="json"))
            get_logger("protocol.events").exception("background_run_failed", run_id=str(run_id), error_type=type(exc).__name__)


@app.get("/runs/{run_id}")
async def get_run(run_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    run = await WorkingMemoryStore(session).get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return run


@app.get("/runs/{run_id}/summary")
async def get_run_summary(run_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    run = await WorkingMemoryStore(session).get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")
    return _build_run_summary(run)


@app.post("/runs/{run_id}/messages")
async def send_run_message(run_id: UUID, payload: RunMessageCreate, background_tasks: BackgroundTasks) -> dict:
    async with app_state.session_factory() as session:
        store = WorkingMemoryStore(session, auto_commit=True)
        run = await store.get_run(run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="run not found") from None
        await store.add_event(run_id, "user_message", {"message": payload.message})
        await store.set_run_status(run_id, RunStatus.RUNNING)
        background_tasks.add_task(execute_run, run_id)
        return await store.get_run(run_id)


@app.post("/runs/{run_id}/control")
async def control_run(run_id: UUID, payload: RunControlCreate) -> dict:
    async with app_state.session_factory() as session:
        store = WorkingMemoryStore(session, auto_commit=True)
        try:
            return await make_runtime(store).apply_control(run_id, payload.action, payload.payload)
        except KeyError:
            raise HTTPException(status_code=404, detail="run not found") from None
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc


@app.get("/runs/{run_id}/events/stream")
async def stream_run_events(run_id: UUID) -> StreamingResponse:
    async def event_generator():
        seen = 0
        while True:
            async with app_state.session_factory() as session:
                run = await WorkingMemoryStore(session).get_run(run_id)
            if run is None:
                yield "event: error\ndata: {\"detail\":\"run not found\"}\n\n"
                return
            events = run.get("events", [])
            for event in events[seen:]:
                yield f"event: run_event\ndata: {json.dumps(event, ensure_ascii=True)}\n\n"
            seen = len(events)
            if run.get("status") in {RunStatus.COMPLETED.value, RunStatus.FAILED.value, RunStatus.CANCELLED.value}:
                yield f"event: run_status\ndata: {json.dumps({'status': run.get('status')}, ensure_ascii=True)}\n\n"
                return
            await asyncio.sleep(1)

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@app.get("/improvement-proposals")
async def list_improvement_proposals(
    status: ImprovementProposalStatus | None = None,
    run_id: UUID | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    proposals = await WorkingMemoryStore(session).list_improvement_proposals(status=status, run_id=run_id)
    return [proposal.model_dump(mode="json") for proposal in proposals]


@app.post("/improvement-proposals/{proposal_id}/approve")
async def approve_improvement_proposal(proposal_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    store = WorkingMemoryStore(session)
    try:
        proposal = await store.approve_improvement_proposal(proposal_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="improvement proposal not found") from None
    await session.commit()
    return proposal.model_dump(mode="json")


@app.post("/improvement-proposals/{proposal_id}/reject")
async def reject_improvement_proposal(proposal_id: UUID, payload: dict[str, str], session: AsyncSession = Depends(get_session)) -> dict:
    reason = payload.get("reason")
    if not reason:
        raise HTTPException(status_code=400, detail="reject requires reason")
    store = WorkingMemoryStore(session)
    try:
        proposal = await store.reject_improvement_proposal(proposal_id, reason)
    except KeyError:
        raise HTTPException(status_code=404, detail="improvement proposal not found") from None
    await session.commit()
    return proposal.model_dump(mode="json")


@app.post("/improvement-proposals/{proposal_id}/mark-implemented")
async def mark_improvement_proposal_implemented(proposal_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    store = WorkingMemoryStore(session)
    try:
        proposal = await store.mark_improvement_proposal_implemented(proposal_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="improvement proposal not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return proposal.model_dump(mode="json")


@app.post("/improvement-proposals/{proposal_id}/implement")
async def implement_improvement_proposal(proposal_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    store = WorkingMemoryStore(session)
    proposal = await store.get_improvement_proposal(proposal_id)
    if proposal is None:
        raise HTTPException(status_code=404, detail="improvement proposal not found")
    if proposal.status != ImprovementProposalStatus.APPROVED:
        raise HTTPException(status_code=409, detail=f"proposal must be approved before implementation: status={proposal.status.value}")
    implementation_profile = await store.get_registry_item(RegistryKind.WORKER, "improvement-implementation-worker")
    if implementation_profile is None:
        raise HTTPException(status_code=409, detail="registry worker is not seeded: improvement-implementation-worker")
    work_order = WorkOrder(
        id=uuid4(),
        run_id=uuid4(),
        task_type="implement_approved_proposal",
        goal="Apply an approved self-improvement proposal through a controlled implementation handler.",
        worker_profile="improvement-implementation-worker",
        worker_type=implementation_profile.spec.get("worker_type", "sandboxed_subprocess"),
        inputs={"proposal": proposal.model_dump(mode="json")},
        output_schema=implementation_profile.spec.get("output_schema", {}),
        allowed_tools=[],
        budget=implementation_profile.spec.get("budget", {}),
        external_action_policy=implementation_profile.spec.get("external_action_policy", {}),
    )
    try:
        worker_output = await L3SandboxExecutor(app_state.hermes).run(
            work_order,
            {"source": "improvement-proposals/implement", "proposal_id": str(proposal.id)},
            implementation_profile.spec,
        )
        implementation_result = dict(worker_output["implementation_result"])
        implementation_result["_worker_execution"] = worker_output.get("_worker_execution", {})
        implemented = await store.implement_improvement_proposal(proposal_id, implementation_result)
        await store.add_event(
            implemented.run_id,
            "improvement_proposal_implemented",
            {"proposal_id": str(implemented.id), "implementation_result": implementation_result},
        )
    except L3WorkerExecutionError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except KeyError:
        raise HTTPException(status_code=404, detail="improvement proposal not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return implemented.model_dump(mode="json")


@app.post("/improvement-proposals/{proposal_id}/mark-proven")
async def mark_improvement_proposal_proven(
    proposal_id: UUID,
    payload: dict[str, Any] | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    store = WorkingMemoryStore(session)
    try:
        proposal = await store.mark_improvement_proposal_proven(proposal_id, proof_result=payload or {})
    except KeyError:
        raise HTTPException(status_code=404, detail="improvement proposal not found") from None
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    await session.commit()
    return proposal.model_dump(mode="json")


@app.get("/failure-learnings")
async def list_failure_learnings(
    status: FailureLearningStatus | None = None,
    playbook_key: str | None = None,
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    learnings = await WorkingMemoryStore(session).list_failure_learnings(status=status, playbook_key=playbook_key)
    return [learning.model_dump(mode="json") for learning in learnings]


@app.post("/system-reviews/recent")
async def create_recent_system_review(payload: RecentSystemReviewCreate, session: AsyncSession = Depends(get_session)) -> dict:
    store = WorkingMemoryStore(session)
    recent_runs = await store.list_recent_runs(limit=payload.limit, playbook_key=payload.playbook_key, since_hours=payload.since_hours)
    learnings = await store.list_failure_learnings(
        status=FailureLearningStatus.ACTIVE,
        playbook_key=payload.playbook_key,
        since_hours=payload.since_hours,
    )
    reviewer_profile = await store.get_registry_item(RegistryKind.WORKER, "self-improvement-reviewer")
    if reviewer_profile is None:
        raise HTTPException(status_code=409, detail="registry worker is not seeded: self-improvement-reviewer")
    work_order = WorkOrder(
        id=uuid4(),
        run_id=uuid4(),
        task_type="review_recent_runs",
        goal="Review recent real runs and produce a prioritized self-improvement backlog.",
        worker_profile="self-improvement-reviewer",
        worker_type=reviewer_profile.spec.get("worker_type", "sandboxed_subprocess"),
        inputs={
            "recent_runs": recent_runs,
            "failure_learnings": [learning.model_dump(mode="json") for learning in learnings],
            "limit": payload.limit,
            "playbook_key": payload.playbook_key,
        },
        output_schema=reviewer_profile.spec.get("output_schema", {}),
        allowed_tools=[],
        budget=reviewer_profile.spec.get("budget", {}),
        external_action_policy=reviewer_profile.spec.get("external_action_policy", {}),
    )
    worker_output = await L3SandboxExecutor(app_state.hermes).run(
        work_order,
        {"source": "system-reviews/recent", "real_run_count": len(recent_runs)},
        reviewer_profile.spec,
    )
    review = SystemReview.model_validate(worker_output["system_review"])
    review.worker_execution = worker_output.get("_worker_execution", {})
    created_proposal_ids: list[str] = []
    for learning in learnings:
        if learning.occurrence_count < 2:
            continue
        if await store.has_open_improvement_proposal(learning.failure_signature, learning.target_component):
            continue
        proposal = await store.add_improvement_proposal(proposal_from_failure_learning(learning))
        created_proposal_ids.append(str(proposal.id))
    review.created_proposal_ids = created_proposal_ids
    review = await store.add_system_review(review)
    await session.commit()
    return review.model_dump(mode="json")


@app.get("/system-reviews")
async def list_system_reviews(playbook_key: str | None = None, session: AsyncSession = Depends(get_session)) -> list[dict]:
    reviews = await WorkingMemoryStore(session).list_system_reviews(playbook_key=playbook_key)
    return [review.model_dump(mode="json") for review in reviews]


@app.get("/reports/system-learning")
async def get_system_learning_report(
    playbook_key: str | None = None,
    since_hours: int | None = None,
    session: AsyncSession = Depends(get_session),
) -> dict:
    store = WorkingMemoryStore(session)
    active_learnings = await store.list_failure_learnings(
        status=FailureLearningStatus.ACTIVE,
        playbook_key=playbook_key,
        since_hours=since_hours,
    )
    resolved_learnings = await store.list_failure_learnings(
        status=FailureLearningStatus.RESOLVED,
        playbook_key=playbook_key,
        since_hours=since_hours,
    )
    proposals = [
        proposal
        for proposal in await store.list_improvement_proposals()
        if await _proposal_matches_scope(store, proposal, playbook_key=playbook_key, since_hours=since_hours)
    ]
    regression_cases = await store.list_regression_cases(playbook_key=playbook_key)
    report = build_system_learning_report(
        active_learnings=active_learnings,
        resolved_learnings=resolved_learnings,
        proposals=proposals,
        regression_cases=regression_cases,
    )
    report['scope'] = {
        'playbook_key': playbook_key,
        'since_hours': since_hours,
        'generated_at': datetime.now(UTC).isoformat(),
    }
    return report


@app.get("/regression-cases")
async def list_regression_cases(playbook_key: str | None = None, session: AsyncSession = Depends(get_session)) -> list[dict]:
    cases = await WorkingMemoryStore(session).list_regression_cases(playbook_key=playbook_key)
    return [case.model_dump(mode="json") for case in cases]


async def _proposal_matches_scope(
    store: WorkingMemoryStore,
    proposal: ImprovementProposal,
    *,
    playbook_key: str | None,
    since_hours: int | None,
) -> bool:
    if since_hours is not None and proposal.created_at is not None:
        cutoff = datetime.now(UTC) - timedelta(hours=since_hours)
        if proposal.created_at < cutoff:
            return False
    if playbook_key is None:
        return True
    proof_spec = proposal.proof_spec if isinstance(proposal.proof_spec, dict) else {}
    scoped_playbook = proof_spec.get('playbook_key')
    if isinstance(scoped_playbook, str) and scoped_playbook:
        return scoped_playbook == playbook_key
    try:
        run = await store.get_run(UUID(proposal.source_run_id))
    except (TypeError, ValueError):
        return False
    return isinstance(run, dict) and run.get('playbook_key') == playbook_key


async def list_hub_items(kind: RegistryKind, session: AsyncSession) -> list[dict]:
    store = WorkingMemoryStore(session)
    items = await store.list_registry_items(kind)
    return [item.model_dump(mode="json") for item in items]


async def get_hub_registry_item(kind: RegistryKind, key: str, session: AsyncSession) -> dict:
    store = WorkingMemoryStore(session)
    item = await store.get_registry_item(kind, key)
    if item is None:
        raise HTTPException(status_code=404, detail="registry item not found")
    return item.model_dump(mode="json")


async def create_hub_registry_change_candidate(payload: RegistryChangeCandidateCreate, session: AsyncSession) -> dict:
    store = WorkingMemoryStore(session)
    candidate = await store.create_registry_change_candidate(payload)
    await session.commit()
    return candidate.model_dump(mode="json")


async def approve_hub_registry_change_candidate(candidate_id: UUID, session: AsyncSession) -> dict:
    store = WorkingMemoryStore(session)
    try:
        candidate = await store.approve_registry_change_candidate(candidate_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="registry change candidate not found") from None
    await session.commit()
    return candidate.model_dump(mode="json")


async def reject_hub_registry_change_candidate(candidate_id: UUID, session: AsyncSession) -> dict:
    store = WorkingMemoryStore(session)
    try:
        candidate = await store.reject_registry_change_candidate(candidate_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="registry change candidate not found") from None
    await session.commit()
    return candidate.model_dump(mode="json")


async def sync_hub_registry_from_yaml(session: AsyncSession) -> dict:
    store = WorkingMemoryStore(session)
    items = yaml_registry_items(app_state.settings.procedural_registry_path)
    for item in items:
        await store.upsert_registry_item(item)
    await session.commit()
    return {"synced": len(items)}


@app.post("/hub/change-candidates")
async def create_hub_change_candidate(payload: RegistryChangeCandidateCreate, session: AsyncSession = Depends(get_session)) -> dict:
    return await create_hub_registry_change_candidate(payload, session)


@app.post("/hub/change-candidates/{candidate_id}/approve")
async def approve_hub_change_candidate(candidate_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    return await approve_hub_registry_change_candidate(candidate_id, session)


@app.post("/hub/change-candidates/{candidate_id}/reject")
async def reject_hub_change_candidate(candidate_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    return await reject_hub_registry_change_candidate(candidate_id, session)


@app.post("/hub/sync/yaml")
async def sync_hub_from_yaml(session: AsyncSession = Depends(get_session)) -> dict:
    return await sync_hub_registry_from_yaml(session)


@app.get("/hub/{kind}")
async def list_hub(kind: str, session: AsyncSession = Depends(get_session)) -> list[dict]:
    return await list_hub_items(normalize_hub_kind(kind), session)


@app.get("/hub/{kind}/{key}")
async def get_hub_item(kind: str, key: str, session: AsyncSession = Depends(get_session)) -> dict:
    return await get_hub_registry_item(normalize_hub_kind(kind), key, session)


def main() -> None:
    uvicorn.run("l2l3_protocol.api.main:app", host="0.0.0.0", port=8080, log_config=None, access_log=False)
