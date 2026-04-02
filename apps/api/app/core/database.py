"""Database engine and session wiring."""

from collections.abc import AsyncGenerator, Generator
import logging

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
async_engine = create_async_engine(settings.database_url, pool_pre_ping=True)
AsyncSessionLocal = async_sessionmaker(bind=async_engine, autoflush=False, autocommit=False)


def get_sync_db() -> Generator[Session, None, None]:
    """Yield a sync request-scoped SQLAlchemy session."""

    logger.debug("Opening sync database session")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
        logger.debug("Closed sync database session")


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async request-scoped SQLAlchemy session."""

    logger.debug("Opening async database session")
    async with AsyncSessionLocal() as db:
        yield db
    logger.debug("Closed async database session")
