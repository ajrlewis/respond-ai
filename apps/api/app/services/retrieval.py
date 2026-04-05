"""Hybrid retrieval service for semantic and keyword search."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from uuid import UUID

from sqlalchemy import Select, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Document, DocumentChunk
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class RetrievedChunk:
    """Unified retrieval payload."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_filename: str
    chunk_index: int
    text: str
    score: float
    retrieval_method: str
    metadata: dict


class RetrievalService:
    """Provides hybrid retrieval capabilities over pgvector + Postgres FTS."""

    def __init__(self, db: AsyncSession, embedding_service: EmbeddingService | None = None) -> None:
        self.db = db
        self.embedding_service = embedding_service

    async def semantic_search(self, query: str, top_k: int = 8) -> list[RetrievedChunk]:
        """Search chunks by vector similarity."""

        if not self.embedding_service:
            logger.warning("Semantic search skipped because embedding service is unavailable")
            return []

        logger.debug("Running semantic search top_k=%d query_chars=%d", top_k, len(query))
        query_embedding = await self.embedding_service.aembed_text(
            query,
            purpose="query_embedding",
            request_metadata={"top_k": top_k},
        )
        distance = DocumentChunk.embedding.cosine_distance(query_embedding)

        stmt: Select = (
            select(
                DocumentChunk.id,
                DocumentChunk.document_id,
                Document.title,
                Document.filename,
                DocumentChunk.chunk_index,
                DocumentChunk.chunk_text,
                DocumentChunk.metadata_json,
                distance.label("distance"),
            )
            .join(Document, Document.id == DocumentChunk.document_id)
            .order_by(distance, DocumentChunk.id.asc())
            .limit(top_k)
        )

        rows = (await self.db.execute(stmt)).all()
        results = [
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                document_title=row.title,
                document_filename=row.filename,
                chunk_index=row.chunk_index,
                text=row.chunk_text,
                score=max(0.0, 1.0 - float(row.distance)),
                retrieval_method="semantic",
                metadata=row.metadata_json or {},
            )
            for row in rows
        ]
        logger.debug("Semantic search produced count=%d", len(results))
        return results

    async def keyword_search(self, query: str, top_k: int = 8) -> list[RetrievedChunk]:
        """Search chunks via full-text search with a trigram fallback."""

        logger.debug("Running keyword search top_k=%d query_chars=%d", top_k, len(query))
        stmt = text(
            """
            SELECT
                c.id,
                c.document_id,
                d.title,
                d.filename,
                c.chunk_index,
                c.chunk_text,
                c.metadata,
                ts_rank_cd(to_tsvector('english', c.chunk_text), plainto_tsquery('english', :query)) AS rank
            FROM document_chunks c
            JOIN documents d ON d.id = c.document_id
            WHERE to_tsvector('english', c.chunk_text) @@ plainto_tsquery('english', :query)
            ORDER BY rank DESC, c.id ASC
            LIMIT :top_k
            """
        )
        rows = (await self.db.execute(stmt, {"query": query, "top_k": top_k})).all()

        if not rows:
            logger.debug("Keyword FTS returned no rows; falling back to trigram similarity")
            fallback_stmt = text(
                """
                SELECT
                    c.id,
                    c.document_id,
                    d.title,
                    d.filename,
                    c.chunk_index,
                    c.chunk_text,
                    c.metadata,
                    similarity(c.chunk_text, :query) AS rank
                FROM document_chunks c
                JOIN documents d ON d.id = c.document_id
                WHERE c.chunk_text ILIKE '%' || :query || '%'
                ORDER BY rank DESC, c.id ASC
                LIMIT :top_k
                """
            )
            rows = (await self.db.execute(fallback_stmt, {"query": query, "top_k": top_k})).all()

        results = [
            RetrievedChunk(
                chunk_id=row.id,
                document_id=row.document_id,
                document_title=row.title,
                document_filename=row.filename,
                chunk_index=row.chunk_index,
                text=row.chunk_text,
                score=float(row.rank or 0.0),
                retrieval_method="keyword",
                metadata=row.metadata or {},
            )
            for row in rows
        ]
        logger.debug("Keyword search produced count=%d", len(results))
        return results

    async def expand_chunk_context(self, chunk_id: UUID, window: int = 1) -> list[RetrievedChunk]:
        """Fetch neighboring chunks from the same document for richer context."""

        logger.debug("Expanding chunk context chunk_id=%s window=%d", chunk_id, window)
        target = await self.db.get(DocumentChunk, chunk_id)
        if not target:
            logger.warning("Chunk context expansion skipped; chunk not found chunk_id=%s", chunk_id)
            return []

        stmt = (
            select(DocumentChunk, Document)
            .join(Document, Document.id == DocumentChunk.document_id)
            .where(DocumentChunk.document_id == target.document_id)
            .where(DocumentChunk.chunk_index >= max(0, target.chunk_index - window))
            .where(DocumentChunk.chunk_index <= target.chunk_index + window)
            .order_by(DocumentChunk.chunk_index)
        )
        rows = (await self.db.execute(stmt)).all()
        results = [
            RetrievedChunk(
                chunk_id=row.DocumentChunk.id,
                document_id=row.DocumentChunk.document_id,
                document_title=row.Document.title,
                document_filename=row.Document.filename,
                chunk_index=row.DocumentChunk.chunk_index,
                text=row.DocumentChunk.chunk_text,
                score=1.0,
                retrieval_method="context_expand",
                metadata=row.DocumentChunk.metadata_json or {},
            )
            for row in rows
        ]
        logger.debug("Expanded chunk context count=%d chunk_id=%s", len(results), chunk_id)
        return results

    async def hybrid_search(self, query: str, top_k: int = 10) -> list[RetrievedChunk]:
        """Combine semantic + keyword retrieval into a single candidate set."""

        logger.debug("Running hybrid search top_k=%d", top_k)
        semantic = await self.semantic_search(query, top_k=top_k)
        keyword = await self.keyword_search(query, top_k=top_k)
        merged: dict[UUID, RetrievedChunk] = {}

        for item in semantic + keyword:
            current = merged.get(item.chunk_id)
            if current is None or item.score > current.score:
                merged[item.chunk_id] = item

        ranked = sorted(
            merged.values(),
            key=lambda chunk: (-float(chunk.score), str(chunk.chunk_id)),
        )
        results = ranked[:top_k]
        logger.debug(
            "Hybrid search merged semantic=%d keyword=%d unique=%d returned=%d",
            len(semantic),
            len(keyword),
            len(merged),
            len(results),
        )
        return results


def chunk_to_dict(chunk: RetrievedChunk) -> dict:
    """Serialize retrieved chunk for graph state and API payloads."""

    return {
        "chunk_id": str(chunk.chunk_id),
        "document_id": str(chunk.document_id),
        "document_title": chunk.document_title,
        "document_filename": chunk.document_filename,
        "chunk_index": chunk.chunk_index,
        "text": chunk.text,
        "score": chunk.score,
        "retrieval_method": chunk.retrieval_method,
        "metadata": chunk.metadata,
    }
