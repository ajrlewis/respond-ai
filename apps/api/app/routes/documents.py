"""Document routes."""

import logging

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_current_user
from app.core.database import get_db
from app.db.models import Document
from app.schemas.documents import DocumentOut

router = APIRouter(prefix="/api/documents", tags=["documents"], dependencies=[Depends(require_current_user)])
logger = logging.getLogger(__name__)


@router.get("", response_model=list[DocumentOut])
async def list_documents(db: AsyncSession = Depends(get_db)) -> list[DocumentOut]:
    """List ingested source documents."""

    logger.debug("Listing ingested documents")
    docs = list((await db.execute(select(Document).order_by(Document.created_at.desc()))).scalars().all())
    logger.info("Returning document list count=%d", len(docs))
    return [
        DocumentOut(
            id=doc.id,
            filename=doc.filename,
            title=doc.title,
            source_type=doc.source_type,
            metadata=doc.metadata_json or {},
            created_at=doc.created_at,
        )
        for doc in docs
    ]
