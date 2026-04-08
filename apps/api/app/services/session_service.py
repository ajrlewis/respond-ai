"""Session access helpers."""

from __future__ import annotations

import logging
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import RFPSession

logger = logging.getLogger(__name__)


class SessionService:
    """Manage business workflow session records."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_session(self, session_id: UUID) -> RFPSession | None:
        logger.debug("Fetching session by id session_id=%s", session_id)
        session = await self.db.get(RFPSession, session_id)
        if not session:
            logger.debug("Session not found session_id=%s", session_id)
        return session

    async def get_session_by_thread_id(self, thread_id: str) -> RFPSession | None:
        logger.debug("Fetching session by thread_id=%s", thread_id)
        # Force refresh from the database so callers don't reuse a stale identity-map
        # instance after another async workflow run updates the same session row.
        stmt = (
            select(RFPSession)
            .where(RFPSession.graph_thread_id == thread_id)
            .execution_options(populate_existing=True)
        )
        session = (await self.db.execute(stmt)).scalar_one_or_none()
        if not session:
            logger.debug("Session not found for thread_id=%s", thread_id)
            return None
        # Even with populate_existing, AsyncSession may still return an identity-mapped
        # instance with stale column values after another session commits updates.
        await self.db.refresh(session)
        return session

    async def create_or_get_session(self, *, thread_id: str, question_text: str, tone: str) -> RFPSession:
        """Create workflow session if missing; otherwise return existing session for thread id."""

        existing = await self.get_session_by_thread_id(thread_id)
        if existing:
            return existing

        session = RFPSession(
            graph_thread_id=thread_id,
            question_text=question_text,
            tone=tone,
            status="draft",
            current_node="ask",
        )
        self.db.add(session)
        await self.db.commit()
        await self.db.refresh(session)
        logger.info("Created new session session_id=%s thread_id=%s", session.id, thread_id)
        return session

    async def persist(self) -> None:
        logger.debug("Persisting session changes")
        await self.db.commit()

    async def refresh(self, session: RFPSession) -> RFPSession:
        logger.debug("Refreshing session session_id=%s", session.id)
        await self.db.refresh(session)
        return session
