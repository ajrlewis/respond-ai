"""Session and ask endpoint schemas."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.documents import EvidenceChunk


class AskRequest(BaseModel):
    """Incoming question payload."""

    question_text: str = Field(min_length=10, max_length=4000)
    tone: str = Field(default="formal", pattern="^(concise|detailed|formal)$")
    thread_id: str | None = Field(default=None, min_length=1, max_length=128)


class ConfidenceOut(BaseModel):
    """Structured confidence payload for review decisions."""

    score: float | None = None
    compliance_status: Literal["passed", "needs_review", "unknown"] = "unknown"
    model_notes: str = ""
    retrieval_notes: str = ""
    evidence_gaps: list[str] = Field(default_factory=list)


class AnswerVersionOut(BaseModel):
    """Stored draft snapshot used for revision history and diffing."""

    version_id: str
    version_number: int
    label: str
    stage: Literal["draft", "revision", "final"]
    answer_text: str
    content: str
    status: Literal["draft", "approved", "historical"]
    is_current: bool = False
    is_approved: bool = False
    revision_feedback: str | None = None
    included_chunk_ids: list[str] = Field(default_factory=list)
    excluded_chunk_ids: list[str] = Field(default_factory=list)
    question_type: str | None = None
    confidence_notes: str | None = None
    confidence_score: float | None = None
    created_at: datetime


class SessionOut(BaseModel):
    """RFP session response."""

    id: UUID
    question_text: str
    question_type: str | None
    tone: str
    status: str
    current_node: str | None
    draft_answer: str | None
    final_answer: str | None
    final_version_number: int | None = None
    approved_at: datetime | None = None
    reviewer_action: str | None = None
    reviewer_id: str | None = None
    evidence_gap_count: int = 0
    requires_gap_acknowledgement: bool = False
    evidence_gaps_acknowledged: bool = False
    evidence_gaps_acknowledged_at: datetime | None = None
    confidence_notes: str | None
    confidence: ConfidenceOut
    evidence: list[EvidenceChunk] = Field(default_factory=list)
    answer_versions: list[AnswerVersionOut] = Field(default_factory=list)
    final_audit: dict = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime


class AskResponse(BaseModel):
    """Ask endpoint payload."""

    session: SessionOut
