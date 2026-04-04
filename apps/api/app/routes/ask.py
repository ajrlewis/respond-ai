"""Question ask/query routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_current_user
from app.core.database import get_db
from app.graph.runtime import run_until_human_review
from app.routes.utils import session_to_schema
from app.schemas.audit import FinalAuditOut
from app.schemas.drafts import DraftCompareOut
from app.schemas.sessions import AnswerVersionOut
from app.schemas.sessions import AskRequest, AskResponse, SessionOut
from app.services.draft_history import compare_session_drafts, get_session_draft, list_session_drafts
from app.services.session_service import SessionService

router = APIRouter(prefix="/api/questions", tags=["questions"], dependencies=[Depends(require_current_user)])
logger = logging.getLogger(__name__)


@router.post("/ask", response_model=AskResponse)
async def ask_question(payload: AskRequest, db: AsyncSession = Depends(get_db)) -> AskResponse:
    """Create a new RFP session and run graph until review pause."""

    question_text = payload.question_text.strip()
    logger.info(
        "Ask request received tone=%s question_chars=%d",
        payload.tone,
        len(question_text),
    )

    thread_id = (payload.thread_id or "").strip() or str(uuid.uuid4())
    logger.debug("Starting workflow execution for thread_id=%s", thread_id)
    await run_until_human_review(
        {
            "thread_id": thread_id,
            "question_text": question_text,
            "tone": payload.tone,
        },
        thread_id=thread_id,
    )
    logger.info("Workflow paused for human review thread_id=%s", thread_id)

    service = SessionService(db)
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
