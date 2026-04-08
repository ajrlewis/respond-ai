"""Schemas for multi-question response documents and versions."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, Field

from app.schemas.documents import EvidenceChunk


class ResponseQuestionOut(BaseModel):
    """Question in a response document."""

    id: UUID
    order_index: int
    extracted_text: str
    normalized_title: str | None = None


class ResponseSectionOut(BaseModel):
    """Answer content for one question in a version."""

    id: UUID
    question_id: UUID
    order_index: int
    content_markdown: str
    confidence_score: float | None = None
    coverage_score: float | None = None
    evidence_refs: list[EvidenceChunk] = Field(default_factory=list)


class ResponseVersionSummaryOut(BaseModel):
    """Version metadata summary for selectors and history."""

    id: UUID
    version_number: int
    label: str
    created_by: str | None = None
    parent_version_id: UUID | None = None
    is_final: bool = False
    created_at: datetime


class ResponseVersionOut(ResponseVersionSummaryOut):
    """Expanded version with section content."""

    sections: list[ResponseSectionOut] = Field(default_factory=list)


class ResponseDocumentOut(BaseModel):
    """Full response document view for the editor."""

    id: UUID
    title: str
    source_filename: str | None = None
    status: str
    created_at: datetime
    updated_at: datetime
    questions: list[ResponseQuestionOut] = Field(default_factory=list)
    versions: list[ResponseVersionSummaryOut] = Field(default_factory=list)
    selected_version: ResponseVersionOut | None = None


class CreateResponseDocumentRequest(BaseModel):
    """Create a response document from provided source/questions."""

    title: str | None = None
    source_filename: str | None = None
    source_text: str | None = None
    questions: list[str] = Field(default_factory=list)
    use_example_questions: bool = False
    created_by: str | None = None


class GenerateResponseDocumentRequest(BaseModel):
    """Generate answers for all questions in a response document."""

    tone: Literal["concise", "detailed", "formal"] = "formal"
    created_by: str | None = None


class SaveSectionInput(BaseModel):
    """Draft section input for creating a new saved version."""

    question_id: UUID
    content_markdown: str
    evidence_refs: list[EvidenceChunk] = Field(default_factory=list)
    confidence_score: float | None = None
    coverage_score: float | None = None


class SaveResponseVersionRequest(BaseModel):
    """Persist a new saved version snapshot."""

    label: str | None = None
    based_on_version_id: UUID | None = None
    created_by: str | None = None
    sections: list[SaveSectionInput] = Field(default_factory=list)


class CompareResponseVersionsOut(BaseModel):
    """Human-readable diff payload for two versions."""

    left: ResponseVersionSummaryOut
    right: ResponseVersionSummaryOut
    segments: list[dict] = Field(default_factory=list)
    section_diffs: list[dict] = Field(default_factory=list)


class AIReviseRequest(BaseModel):
    """Apply AI-assisted revision instructions without auto-saving a version."""

    instruction: str = Field(min_length=4, max_length=4000)
    tone: Literal["concise", "detailed", "formal"] = "formal"
    base_version_id: UUID | None = None
    question_id: UUID | None = None
    selected_text: str | None = None


class AIReviseResponse(BaseModel):
    """AI revision suggestions that can be applied as unsaved edits."""

    base_version_id: UUID
    revised_sections: list[SaveSectionInput] = Field(default_factory=list)
