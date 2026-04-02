"""Seed data ingestion for markdown documents."""

from __future__ import annotations

from dataclasses import dataclass
import logging
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Document, DocumentChunk
from app.services.chunking import chunk_markdown
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class IngestionSummary:
    """Simple ingestion result payload."""

    documents_processed: int
    chunks_processed: int


class IngestionService:
    """Reads markdown docs, chunks, embeds, and stores them."""

    def __init__(self, db: Session, embedding_service: EmbeddingService | None = None) -> None:
        self.db = db
        self.embedding_service = embedding_service or EmbeddingService()

    def ingest_markdown_directory(self, docs_dir: Path) -> IngestionSummary:
        """Ingest every markdown file in a directory."""

        files = sorted(docs_dir.glob("*.md"))
        logger.info("Starting markdown ingestion directory=%s file_count=%d", docs_dir, len(files))
        documents_processed = 0
        chunks_processed = 0

        for file_path in files:
            logger.debug("Ingesting document filename=%s", file_path.name)
            text = file_path.read_text(encoding="utf-8")
            title = self._extract_title(text, default=file_path.stem.replace("_", " ").title())

            existing = self.db.execute(select(Document).where(Document.filename == file_path.name)).scalar_one_or_none()
            if existing:
                logger.debug("Replacing existing document filename=%s document_id=%s", file_path.name, existing.id)
                self.db.delete(existing)
                self.db.flush()

            document = Document(
                filename=file_path.name,
                title=title,
                source_type="internal_markdown",
                raw_text=text,
                metadata_json={"path": str(file_path)},
            )
            self.db.add(document)
            self.db.flush()

            chunk_candidates = chunk_markdown(markdown_text=text, source_filename=file_path.name)
            logger.debug("Chunked document filename=%s chunks=%d", file_path.name, len(chunk_candidates))
            embeddings = self.embedding_service.embed_texts(
                [chunk.text for chunk in chunk_candidates],
                purpose="seed_embedding",
                request_metadata={"source_filename": file_path.name},
            )

            for candidate, embedding in zip(chunk_candidates, embeddings, strict=True):
                chunk = DocumentChunk(
                    document_id=document.id,
                    chunk_index=candidate.chunk_index,
                    chunk_text=candidate.text,
                    metadata_json=candidate.metadata,
                    embedding=embedding,
                )
                self.db.add(chunk)
                chunks_processed += 1

            documents_processed += 1

        self.db.commit()
        logger.info(
            "Completed markdown ingestion documents_processed=%d chunks_processed=%d",
            documents_processed,
            chunks_processed,
        )
        return IngestionSummary(documents_processed=documents_processed, chunks_processed=chunks_processed)

    @staticmethod
    def _extract_title(markdown_text: str, default: str) -> str:
        for line in markdown_text.splitlines():
            if line.startswith("# "):
                return line.replace("# ", "", 1).strip()
        return default
