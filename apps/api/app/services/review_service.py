"""Review persistence helpers."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RFPSession, RFPReview

logger = logging.getLogger(__name__)


class ReviewService:
    """Manage reviewer actions."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_review(
        self,
        session_id: UUID,
        reviewer_action: str,
        reviewer_id: str | None,
        review_comments: str | None,
        edited_answer: str | None,
        excluded_evidence_keys: list[str],
        evidence_gaps_acknowledged: bool,
        has_evidence_gaps: bool,
    ) -> RFPReview:
        logger.info("Creating review session_id=%s action=%s", session_id, reviewer_action)
        acknowledged_at = datetime.now(UTC) if has_evidence_gaps and evidence_gaps_acknowledged else None
        session = await self.db.get(RFPSession, session_id)
        if session and has_evidence_gaps and evidence_gaps_acknowledged:
            session.evidence_gaps_acknowledged = True
            session.evidence_gaps_acknowledged_at = acknowledged_at

        review = RFPReview(
            session_id=session_id,
            reviewer_action=reviewer_action,
            reviewer_id=reviewer_id,
            review_comments=review_comments,
            edited_answer=edited_answer,
            excluded_evidence_keys=excluded_evidence_keys,
            reviewed_evidence_gaps=evidence_gaps_acknowledged,
            evidence_gaps_acknowledged_at=acknowledged_at,
        )
        self.db.add(review)
        await self.db.commit()
        await self.db.refresh(review)
        logger.debug("Review created review_id=%s session_id=%s", review.id, session_id)
        return review

    async def list_reviews(self, session_id: UUID) -> list[RFPReview]:
        logger.debug("Listing reviews session_id=%s", session_id)
        stmt = (
            select(RFPReview)
            .where(RFPReview.session_id == session_id)
            .order_by(RFPReview.created_at.asc())
        )
        reviews = list((await self.db.execute(stmt)).scalars().all())
        logger.debug("Listed reviews session_id=%s count=%d", session_id, len(reviews))
        return reviews
