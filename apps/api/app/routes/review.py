"""Review and history routes."""

from __future__ import annotations

import logging
import uuid

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_current_user
from app.core.database import get_db
from app.graph.runtime import resume_from_review
from app.routes.utils import session_to_schema
from app.schemas.reviews import ReviewOut, ReviewRequest, ReviewResponse
from app.services.review_service import ReviewService
from app.services.session_service import SessionService
from app.services.workflow_events import workflow_event_bus

router = APIRouter(prefix="/api/questions", tags=["reviews"], dependencies=[Depends(require_current_user)])
logger = logging.getLogger(__name__)


@router.post("/{session_id}/review", response_model=ReviewResponse)
async def review_session(
    session_id: uuid.UUID,
    payload: ReviewRequest,
    db: AsyncSession = Depends(get_db),
) -> ReviewResponse:
    """Persist a review action and resume the workflow from HITL checkpoint."""

    logger.info(
        "Review request received session_id=%s action=%s",
        session_id,
        payload.reviewer_action,
    )
    session_service = SessionService(db)
    review_service = ReviewService(db)

    session = await session_service.get_session(session_id)
    if not session:
        logger.warning("Review request for missing session session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    if getattr(session, "status", "") == "approved":
        logger.warning("Review request rejected for locked approved session session_id=%s", session_id)
        raise HTTPException(status_code=409, detail="Session is already approved and locked.")

    thread_id = session.graph_thread_id

    if payload.reviewer_action == "revise":
        has_comments = bool(payload.review_comments and payload.review_comments.strip())
        has_exclusions = bool(payload.excluded_evidence_keys)
        if not (has_comments or has_exclusions):
            logger.warning("Review revise request missing comments/exclusions session_id=%s", session_id)
            raise HTTPException(
                status_code=400,
                detail="Provide revision comments or exclude at least one citation chunk.",
            )
    elif payload.edited_answer and payload.edited_answer.strip():
        logger.warning("Approve request rejected due to edited_answer payload session_id=%s", session_id)
        raise HTTPException(
            status_code=400,
            detail="Approve does not accept edited_answer; approve the latest draft as-is.",
        )

    confidence_payload = getattr(session, "confidence_payload", {}) or {}
    evidence_gaps = confidence_payload.get("evidence_gaps", [])
    has_evidence_gaps = bool(evidence_gaps)
    evidence_gaps_acknowledged = (
        bool(payload.evidence_gaps_acknowledged)
        if payload.evidence_gaps_acknowledged is not None
        else bool(payload.reviewed_evidence_gaps)
    )
    session_gap_acknowledged = bool(getattr(session, "evidence_gaps_acknowledged", False))
    effective_gap_acknowledgement = has_evidence_gaps and (evidence_gaps_acknowledged or session_gap_acknowledged)
    if payload.reviewer_action == "approve" and has_evidence_gaps and not (
        effective_gap_acknowledgement
    ):
        logger.warning(
            "Approve blocked due to unacknowledged evidence gaps session_id=%s gap_count=%d",
            session_id,
            len(evidence_gaps),
        )
        raise HTTPException(
            status_code=400,
            detail="Evidence gaps must be acknowledged before approval.",
        )

    await review_service.create_review(
        session_id=session_id,
        reviewer_action=payload.reviewer_action,
        reviewer_id=payload.reviewer_id.strip() if payload.reviewer_id else None,
        review_comments=payload.review_comments,
        edited_answer=payload.edited_answer,
        excluded_evidence_keys=payload.excluded_evidence_keys,
        evidence_gaps_acknowledged=effective_gap_acknowledgement,
        has_evidence_gaps=has_evidence_gaps,
    )
    logger.debug("Review persisted session_id=%s action=%s", session_id, payload.reviewer_action)
    await workflow_event_bus.publish_session(
        session_id=str(session_id),
        reason="review_submitted",
        status=payload.reviewer_action,
    )

    logger.info("Resuming workflow from review thread_id=%s", thread_id)
    try:
        await resume_from_review(
            thread_id=thread_id,
            review_payload={
                "session_id": str(session_id),
                "reviewer_action": payload.reviewer_action,
                "review_comments": payload.review_comments or "",
                "edited_answer": payload.edited_answer or "",
                "reviewer_id": payload.reviewer_id or "",
                "excluded_evidence_keys": payload.excluded_evidence_keys,
                "reviewed_evidence_gaps": effective_gap_acknowledgement,
                "evidence_gaps_acknowledged": effective_gap_acknowledgement,
            },
        )
    except Exception as exc:
        await workflow_event_bus.publish_session(
            session_id=str(session_id),
            reason="workflow_error",
            status="error",
            error=str(exc),
        )
        raise

    refreshed = await session_service.get_session(session_id)
    if not refreshed:
        logger.error("Session missing after review resume session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found after review")

    await db.refresh(refreshed)
    logger.info(
        "Review response ready session_id=%s status=%s",
        refreshed.id,
        refreshed.status,
    )
    return ReviewResponse(session=session_to_schema(refreshed))


@router.get("/{session_id}/history", response_model=list[ReviewOut])
async def review_history(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)) -> list[ReviewOut]:
    """Return review history for a session."""

    logger.debug("Review history requested session_id=%s", session_id)
    session_service = SessionService(db)
    if not await session_service.get_session(session_id):
        logger.warning("Review history requested for missing session session_id=%s", session_id)
        raise HTTPException(status_code=404, detail="Session not found")

    review_service = ReviewService(db)
    reviews = await review_service.list_reviews(session_id)
    logger.debug("Review history fetched session_id=%s count=%d", session_id, len(reviews))

    return [
        ReviewOut(
            id=item.id,
            session_id=item.session_id,
            reviewer_action=item.reviewer_action,
            reviewer_id=item.reviewer_id,
            review_comments=item.review_comments,
            edited_answer=item.edited_answer,
            excluded_evidence_keys=item.excluded_evidence_keys or [],
            reviewed_evidence_gaps=bool(item.reviewed_evidence_gaps),
            evidence_gaps_acknowledged=bool(item.reviewed_evidence_gaps),
            evidence_gaps_acknowledged_at=getattr(item, "evidence_gaps_acknowledged_at", None),
            created_at=item.created_at,
        )
        for item in reviews
    ]
