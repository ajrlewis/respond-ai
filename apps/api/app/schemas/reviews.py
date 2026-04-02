"""Review endpoint schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.sessions import SessionOut


class ReviewRequest(BaseModel):
    """Review action payload."""

    reviewer_action: str = Field(pattern="^(approve|revise)$")
    reviewer_id: str | None = Field(default=None, max_length=128)
    review_comments: str | None = Field(default=None, max_length=3000)
    edited_answer: str | None = Field(default=None, max_length=10000)
    excluded_evidence_keys: list[str] = Field(default_factory=list)
    reviewed_evidence_gaps: bool = False
    evidence_gaps_acknowledged: bool | None = None


class ReviewOut(BaseModel):
    """Review record."""

    id: UUID
    session_id: UUID
    reviewer_action: str
    reviewer_id: str | None
    review_comments: str | None
    edited_answer: str | None
    excluded_evidence_keys: list[str] = Field(default_factory=list)
    reviewed_evidence_gaps: bool
    evidence_gaps_acknowledged: bool = False
    evidence_gaps_acknowledged_at: datetime | None = None
    created_at: datetime


class ReviewResponse(BaseModel):
    """Review endpoint payload."""

    session: SessionOut
