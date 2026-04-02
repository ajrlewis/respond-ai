"""Structured outputs for question classification and evidence synthesis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


QuestionType = Literal[
    "strategy",
    "esg",
    "track_record",
    "risk",
    "operations",
    "team",
    "differentiation",
    "other",
]

RetrievalStrategy = Literal["semantic", "keyword", "hybrid"]


class QuestionClassificationResult(BaseModel):
    """Typed result for initial question triage."""

    question_type: QuestionType = Field(description="Best-fit question type label.")
    reasoning_summary: str = Field(
        default="",
        description="Short explanation of why the type was selected.",
    )
    suggested_retrieval_strategy: RetrievalStrategy = Field(
        default="hybrid",
        description="Recommended retrieval method mix.",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Classifier confidence from 0-1.")


class EvidenceSynthesisResult(BaseModel):
    """Structured evidence cross-reference output."""

    selected_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk ids that should remain in final evidence set.",
    )
    rejected_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk ids rejected as weak, duplicate, or irrelevant.",
    )
    contradictions_found: list[str] = Field(
        default_factory=list,
        description="Conflicting facts discovered across evidence.",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Material gaps that block a complete answer.",
    )
    evidence_summary: str = Field(
        default="",
        description="Concise summary of grounded evidence coverage.",
    )
