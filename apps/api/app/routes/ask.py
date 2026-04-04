"""Question ask/query routes."""

from __future__ import annotations

import asyncio
import logging
from typing import Any, Awaitable, Callable
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_current_user
from app.core.database import AsyncSessionLocal, get_db
from app.graph.runtime import run_until_human_review
from app.routes.utils import session_to_schema
from app.schemas.audit import FinalAuditOut
from app.schemas.drafts import DraftCompareOut
from app.schemas.sessions import AnswerVersionOut
from app.schemas.sessions import AskRequest, AskResponse, SessionOut
from app.services.draft_history import compare_session_drafts, get_session_draft, list_session_drafts
from app.services.session_service import SessionService
from app.services.workflow_events import WorkflowEvent, format_sse_comment, format_sse_event, workflow_event_bus

router = APIRouter(prefix="/api/questions", tags=["questions"], dependencies=[Depends(require_current_user)])
logger = logging.getLogger(__name__)


def _build_workflow_event_payload(
    *,
    session: SessionOut | None,
    reason: str,
    signal: WorkflowEvent | None = None,
    error: str | None = None,
    stream_ref: str | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {"reason": reason}
    if signal:
        payload["timestamp"] = signal.timestamp
        if signal.node_name is not None:
            payload["node"] = signal.node_name
        if signal.status is not None:
            payload["status"] = signal.status
        if signal.error:
            payload["error"] = signal.error
    if error:
        payload["error"] = error
    if session is not None:
        payload["session"] = session.model_dump(mode="json")
    if stream_ref is not None:
        payload["stream_ref"] = stream_ref
    return payload


async def _load_session_schema_by_id(session_id: uuid.UUID) -> SessionOut | None:
    async with AsyncSessionLocal() as db:
        session = await SessionService(db).get_session(session_id)
        if not session:
            return None
        return session_to_schema(session)


async def _load_session_schema_by_thread(thread_id: str) -> SessionOut | None:
    async with AsyncSessionLocal() as db:
        session = await SessionService(db).get_session_by_thread_id(thread_id)
        if not session:
            return None
        return session_to_schema(session)


async def _workflow_stream_response(
    *,
    request: Request,
    subscribe: Callable[[], Awaitable[asyncio.Queue[WorkflowEvent]]],
    unsubscribe: Callable[[asyncio.Queue[WorkflowEvent]], Awaitable[None]],
    load_session: Callable[[], Awaitable[SessionOut | None]],
    stream_ref: str,
    allow_initial_missing: bool = False,
) -> StreamingResponse:
    queue = await subscribe()

    async def event_generator():
        try:
            snapshot = await load_session()
            if snapshot is None:
                if allow_initial_missing:
                    yield format_sse_comment("waiting_for_session")
                    snapshot = None
                else:
                    yield format_sse_event(
                        event="workflow_state",
                        data=_build_workflow_event_payload(
                            session=None,
                            reason="session_not_found",
                            error="Session not found.",
                            stream_ref=stream_ref,
                        ),
                    )
                    return

            if snapshot is not None:
                yield format_sse_event(
                    event="workflow_state",
                    data=_build_workflow_event_payload(
                        session=snapshot,
                        reason="snapshot",
                        stream_ref=stream_ref,
                    ),
                )

            while True:
                if await request.is_disconnected():
                    break
                try:
                    signal = await asyncio.wait_for(queue.get(), timeout=15.0)
                except TimeoutError:
                    yield format_sse_comment("keepalive")
                    continue

                try:
                    current = await load_session()
                except Exception as exc:  # pragma: no cover - defensive stream safety
                    logger.warning("Failed to load live session snapshot stream_ref=%s error=%s", stream_ref, exc)
                    yield format_sse_event(
                        event="workflow_state",
                        data=_build_workflow_event_payload(
                            session=None,
                            reason="stream_error",
                            signal=signal,
                            error="Failed to load live workflow state.",
                            stream_ref=stream_ref,
                        ),
                    )
                    continue

                if current is None:
                    if allow_initial_missing:
                        if signal.error:
                            yield format_sse_event(
                                event=signal.event,
                                data=_build_workflow_event_payload(
                                    session=None,
                                    reason=signal.reason,
                                    signal=signal,
                                    stream_ref=stream_ref,
                                ),
                            )
                        continue
                    yield format_sse_event(
                        event="workflow_state",
                        data=_build_workflow_event_payload(
                            session=None,
                            reason="session_not_found",
                            signal=signal,
                            error="Session not found.",
                            stream_ref=stream_ref,
                        ),
                    )
                    break

                yield format_sse_event(
                    event=signal.event,
                    data=_build_workflow_event_payload(
                        session=current,
                        reason=signal.reason,
                        signal=signal,
                        stream_ref=stream_ref,
                    ),
                )
        except asyncio.CancelledError:
            logger.debug("Workflow SSE stream cancelled stream_ref=%s", stream_ref)
            raise
        finally:
            await unsubscribe(queue)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/ask", response_model=AskResponse)
async def ask_question(payload: AskRequest, db: AsyncSession = Depends(get_db)) -> AskResponse:
    """Create a new RFP session and run graph until review pause."""

    question_text = payload.question_text.strip()
    logger.info(
        "Ask request received tone=%s question_chars=%d",
        payload.tone,
        len(question_text),
    )

    service = SessionService(db)
    thread_id = (payload.thread_id or "").strip() or str(uuid.uuid4())
    logger.debug("Starting workflow execution for thread_id=%s", thread_id)
    try:
        await run_until_human_review(
            {
                "thread_id": thread_id,
                "question_text": question_text,
                "tone": payload.tone,
            },
            thread_id=thread_id,
        )
    except Exception as exc:
        await workflow_event_bus.publish_thread(
            thread_id=thread_id,
            reason="workflow_error",
            error=str(exc),
        )
        existing_session = await service.get_session_by_thread_id(thread_id)
        if existing_session:
            await workflow_event_bus.publish_session(
                session_id=str(existing_session.id),
                reason="workflow_error",
                status="error",
                error=str(exc),
            )
        raise
    logger.info("Workflow paused for human review thread_id=%s", thread_id)

    session = await service.get_session_by_thread_id(thread_id)
    if not session:
        logger.error("Workflow finished without persisted session thread_id=%s", thread_id)
        raise HTTPException(status_code=500, detail="Session was not persisted by workflow.")

    await db.refresh(session)
    logger.info("Returning ask response session_id=%s status=%s", session.id, session.status)
    return AskResponse(session=session_to_schema(session))


@router.get("/thread/{thread_id}", response_model=SessionOut)
async def get_session_by_thread_id(thread_id: str, db: AsyncSession = Depends(get_db)) -> SessionOut:
    """Return full session state by graph thread id."""

    logger.debug("Session lookup requested by thread_id=%s", thread_id)
    service = SessionService(db)
    session = await service.get_session_by_thread_id(thread_id)
    if not session:
        logger.warning("Session lookup failed thread_id=%s", thread_id)
        raise HTTPException(status_code=404, detail="Session not found")

    logger.debug("Session lookup succeeded thread_id=%s status=%s", thread_id, session.status)
    return session_to_schema(session)


@router.get("/{session_id}/events")
async def stream_session_events(
    session_id: uuid.UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream workflow state updates for a session using SSE."""

    service = SessionService(db)
    session = await service.get_session(session_id)
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    return await _workflow_stream_response(
        request=request,
        subscribe=lambda: workflow_event_bus.subscribe_session(str(session_id)),
        unsubscribe=lambda queue: workflow_event_bus.unsubscribe_session(str(session_id), queue),
        load_session=lambda: _load_session_schema_by_id(session_id),
        stream_ref=f"session:{session_id}",
    )


@router.get("/thread/{thread_id}/events")
async def stream_thread_events(
    thread_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream workflow state updates by graph thread id (bootstrap for ask flow)."""

    service = SessionService(db)
    existing = await service.get_session_by_thread_id(thread_id)
    if existing:
        await workflow_event_bus.register_thread_session(
            thread_id=thread_id,
            session_id=str(existing.id),
        )

    return await _workflow_stream_response(
        request=request,
        subscribe=lambda: workflow_event_bus.subscribe_thread(thread_id),
        unsubscribe=lambda queue: workflow_event_bus.unsubscribe_thread(thread_id, queue),
        load_session=lambda: _load_session_schema_by_thread(thread_id),
        stream_ref=f"thread:{thread_id}",
        allow_initial_missing=True,
    )


@router.get("/{session_id}/drafts", response_model=list[AnswerVersionOut])
async def list_drafts(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[AnswerVersionOut]:
    """Return all draft snapshots for a session."""

    logger.debug("Draft list requested session_id=%s", session_id)
    service = SessionService(db)
    session = await service.get_session(session_id)
    if not session:
        logger.warning("Draft list failed session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    return [AnswerVersionOut.model_validate(item) for item in list_session_drafts(session)]


@router.get("/{session_id}/drafts/compare", response_model=DraftCompareOut)
async def compare_drafts(
    session_id: uuid.UUID,
    left: str = Query(..., min_length=1),
    right: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db),
) -> DraftCompareOut:
    """Compare two draft versions for a session."""

    logger.debug("Draft compare requested session_id=%s left=%s right=%s", session_id, left, right)
    service = SessionService(db)
    session = await service.get_session(session_id)
    if not session:
        logger.warning("Draft compare failed session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    comparison = compare_session_drafts(session, left, right)
    if not comparison:
        logger.warning(
            "Draft compare ids not found session_id=%s left=%s right=%s",
            session_id,
            left,
            right,
        )
        raise HTTPException(status_code=404, detail="Draft version not found")

    return DraftCompareOut.model_validate(comparison)


@router.get("/{session_id}/drafts/{draft_id}", response_model=AnswerVersionOut)
async def get_draft(
    session_id: uuid.UUID,
    draft_id: str,
    db: AsyncSession = Depends(get_db),
) -> AnswerVersionOut:
    """Return a single draft snapshot by id."""

    logger.debug("Draft lookup requested session_id=%s draft_id=%s", session_id, draft_id)
    service = SessionService(db)
    session = await service.get_session(session_id)
    if not session:
        logger.warning("Draft lookup failed session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    draft = get_session_draft(session, draft_id)
    if not draft:
        logger.warning("Draft lookup id not found session_id=%s draft_id=%s", session_id, draft_id)
        raise HTTPException(status_code=404, detail="Draft version not found")

    return AnswerVersionOut.model_validate(draft)


@router.get("/{session_id}/audit", response_model=FinalAuditOut)
async def get_final_audit(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> FinalAuditOut:
    """Return immutable final audit snapshot for an approved session."""

    logger.debug("Final audit requested session_id=%s", session_id)
    service = SessionService(db)
    session = await service.get_session(session_id)
    if not session:
        logger.warning("Final audit lookup failed session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    if session.status != "approved":
        logger.warning("Final audit requested before approval session_id=%s status=%s", session_id, session.status)
        raise HTTPException(status_code=409, detail="Final audit snapshot is available only after approval.")

    audit_payload = getattr(session, "final_audit_payload", {}) or {}
    selected_evidence = audit_payload.get("selected_evidence")
    review_history = audit_payload.get("review_history")
    included_chunk_ids = audit_payload.get("included_chunk_ids")
    excluded_chunk_ids = audit_payload.get("excluded_chunk_ids")
    confidence_payload = audit_payload.get("confidence_payload")

    payload = {
        "session_id": session.id,
        "version_number": audit_payload.get("version_number", getattr(session, "final_version_number", None)),
        "timestamp": audit_payload.get("timestamp", getattr(session, "approved_at", None)),
        "reviewer_action": audit_payload.get("reviewer_action", getattr(session, "reviewer_action", None)),
        "reviewer_id": audit_payload.get("reviewer_id", getattr(session, "reviewer_id", None)),
        "final_answer": audit_payload.get("final_answer", session.final_answer or ""),
        "included_chunk_ids": (
            [str(chunk_id) for chunk_id in included_chunk_ids]
            if isinstance(included_chunk_ids, list)
            else []
        ),
        "excluded_chunk_ids": (
            [str(chunk_id) for chunk_id in excluded_chunk_ids]
            if isinstance(excluded_chunk_ids, list)
            else []
        ),
        "selected_evidence": selected_evidence if isinstance(selected_evidence, list) else [],
        "confidence_score": audit_payload.get("confidence_score"),
        "confidence_notes": audit_payload.get("confidence_notes", session.confidence_notes),
        "confidence_payload": confidence_payload if isinstance(confidence_payload, dict) else {},
        "evidence_gap_count": int(
            audit_payload.get(
                "evidence_gap_count",
                len(((confidence_payload if isinstance(confidence_payload, dict) else {}) or {}).get("evidence_gaps", []) or []),
            )
            or 0
        ),
        "evidence_gaps_acknowledged": bool(
            audit_payload.get("evidence_gaps_acknowledged", getattr(session, "evidence_gaps_acknowledged", False))
        ),
        "evidence_gaps_acknowledged_at": audit_payload.get(
            "evidence_gaps_acknowledged_at",
            getattr(session, "evidence_gaps_acknowledged_at", None),
        ),
        "review_history": review_history if isinstance(review_history, list) else [],
    }
    return FinalAuditOut.model_validate(payload)


@router.get("/{session_id}", response_model=SessionOut)
async def get_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> SessionOut:
    """Return full session state."""

    logger.debug("Session lookup requested session_id=%s", session_id)
    service = SessionService(db)
    session = await service.get_session(session_id)
    if not session:
        logger.warning("Session lookup failed session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    logger.debug("Session lookup succeeded session_id=%s status=%s", session.id, session.status)
    return session_to_schema(session)
