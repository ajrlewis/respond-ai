"""Document and evidence schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class DocumentOut(BaseModel):
    """Document summary payload."""

    id: UUID
    filename: str
    title: str
    source_type: str
    metadata: dict = Field(default_factory=dict)
    created_at: datetime


class EvidenceChunk(BaseModel):
    """Retrieved evidence chunk with citation metadata."""

    chunk_id: UUID
    document_id: UUID
    document_title: str
    document_filename: str
    chunk_index: int
    text: str
    score: float
    retrieval_method: str
    excluded_by_reviewer: bool = False
    metadata: dict = Field(default_factory=dict)


class EvidenceBundle(BaseModel):
    """Evidence response model."""

    items: list[EvidenceChunk]
