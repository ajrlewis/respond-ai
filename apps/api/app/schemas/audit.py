"""Final audit snapshot schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class FinalAuditEvidenceOut(BaseModel):
    """Evidence row captured in the immutable final audit snapshot."""

    chunk_id: str | None = None
    document_id: str | None = None
    document_title: str = ""
    document_filename: str = ""
    chunk_index: int | None = None
    score: float | None = None
    retrieval_method: str = ""
    text: str = ""
    excluded_by_reviewer: bool = False
    metadata: dict = Field(default_factory=dict)


class FinalAuditReviewOut(BaseModel):
    """Reviewer event included in the final audit snapshot history."""

    id: str
    reviewer_action: str
    reviewer_id: str | None = None
    review_comments: str | None = None
    edited_answer: str | None = None
    excluded_evidence_keys: list[str] = Field(default_factory=list)
    reviewed_evidence_gaps: bool = False
    evidence_gaps_acknowledged_at: datetime | None = None
    created_at: datetime


class FinalAuditOut(BaseModel):
    """Dedicated payload for approved session audit retrieval."""

    session_id: UUID
    version_number: int | None = None
    timestamp: datetime | None = None
    reviewer_action: str | None = None
    reviewer_id: str | None = None
    final_answer: str = ""
    included_chunk_ids: list[str] = Field(default_factory=list)
    excluded_chunk_ids: list[str] = Field(default_factory=list)
    selected_evidence: list[FinalAuditEvidenceOut] = Field(default_factory=list)
    confidence_score: float | None = None
    confidence_notes: str | None = None
    confidence_payload: dict = Field(default_factory=dict)
    evidence_gap_count: int = 0
    evidence_gaps_acknowledged: bool = False
    evidence_gaps_acknowledged_at: datetime | None = None
    review_history: list[FinalAuditReviewOut] = Field(default_factory=list)
