from collections.abc import AsyncIterator
import asyncio
from contextlib import asynccontextmanager
import json
from time import perf_counter
from uuid import UUID

import structlog
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Request, Response
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from l2l3_protocol.api.state import app_state, build_memory_router
from l2l3_protocol.config import get_settings
from l2l3_protocol.core.schemas import (
    FailureLearningStatus,
    ImprovementProposalStatus,
    ProcessRun,
    ProcessRunCreate,
    RecentSystemReviewCreate,
    RegistryChangeCandidateCreate,
    RegistryKind,
    RunControlCreate,
    RunMessageCreate,
    RunStatus,
)
from l2l3_protocol.core.terminology import normalize_hub_kind
from l2l3_protocol.db.migrations import run_upgrade_head
from l2l3_protocol.db.session import get_session, make_engine, make_session_factory
from l2l3_protocol.db.store import WorkingMemoryStore
from l2l3_protocol.logging import configure_logging, get_logger
from l2l3_protocol.memory.adapters import ProceduralRegistry
from l2l3_protocol.hub.registry import yaml_registry_items
from l2l3_protocol.runtime.hermes import HermesRuntime
from l2l3_protocol.runtime.process_runtime import ProcessRuntime
from l2l3_protocol.runtime.diagnostics import analyze_run
from l2l3_protocol.runtime.self_improvement import build_failure_learnings, build_recent_system_review, proposal_from_failure_learning


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


@app.post("/improvement-proposals/{proposal_id}/mark-proven")
async def mark_improvement_proposal_proven(proposal_id: UUID, session: AsyncSession = Depends(get_session)) -> dict:
    store = WorkingMemoryStore(session)
    try:
        proposal = await store.mark_improvement_proposal_proven(proposal_id)
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
    recent_runs = await store.list_recent_runs(limit=payload.limit, playbook_key=payload.playbook_key)
    learnings = await store.list_failure_learnings(status=FailureLearningStatus.ACTIVE, playbook_key=payload.playbook_key)
    review = build_recent_system_review(
        recent_runs=recent_runs,
        learnings=learnings,
        limit=payload.limit,
        playbook_key=payload.playbook_key,
    )
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
