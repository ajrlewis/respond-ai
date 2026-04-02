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
        stmt = select(RFPSession).where(RFPSession.graph_thread_id == thread_id)
        session = (await self.db.execute(stmt)).scalar_one_or_none()
        if not session:
            logger.debug("Session not found for thread_id=%s", thread_id)
        return session

    async def persist(self) -> None:
        logger.debug("Persisting session changes")
        await self.db.commit()

    async def refresh(self, session: RFPSession) -> RFPSession:
        logger.debug("Refreshing session session_id=%s", session.id)
        await self.db.refresh(session)
        return session
