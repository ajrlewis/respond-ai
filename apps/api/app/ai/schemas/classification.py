"""Structured outputs for planning, classification, and evidence evaluation."""

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
CoverageLevel = Literal["strong", "partial", "weak"]
RecommendedAction = Literal["proceed", "proceed_with_caveats", "retrieve_more"]


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


class RetrievalPlanResult(BaseModel):
    """Structured plan that guides adaptive retrieval before evidence collection."""

    question_type: QuestionType = Field(description="Best-fit question type label.")
    reasoning_summary: str = Field(
        default="",
        description="Concise explanation of the decomposition and retrieval intent.",
    )
    sub_questions: list[str] = Field(
        default_factory=list,
        description="Sub-questions that should be answered to fully address the prompt.",
    )
    retrieval_strategy: RetrievalStrategy = Field(
        default="hybrid",
        description="Primary retrieval strategy selected for this question.",
    )
    priority_sources: list[str] = Field(
        default_factory=list,
        description="Priority source/doc categories to weight during retrieval.",
    )
    needs_examples: bool = Field(
        default=False,
        description="Whether concrete investment/case examples are important.",
    )
    needs_quantitative_support: bool = Field(
        default=False,
        description="Whether numeric evidence is required for a strong answer.",
    )
    should_expand_context: bool = Field(
        default=False,
        description="Whether neighboring chunk context should be expanded.",
    )
    needs_regulatory_context: bool = Field(
        default=False,
        description="Whether regulatory/policy framing is needed.",
    )
    needs_prior_answers: bool = Field(
        default=False,
        description="Whether prior RFP answers should be prioritized.",
    )
    preferred_top_k: int = Field(
        default=10,
        ge=4,
        le=24,
        description="Suggested retrieval depth before downstream filtering.",
    )
    confidence: float = Field(ge=0.0, le=1.0, description="Planner confidence from 0-1.")


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


class EvidenceEvaluationResult(BaseModel):
    """Structured self-critique of evidence quality before drafting."""

    coverage: CoverageLevel = Field(description="Overall evidence coverage quality.")
    confidence: float = Field(ge=0.0, le=1.0, description="Evaluator confidence from 0-1.")
    selected_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk ids selected for drafting.",
    )
    rejected_chunk_ids: list[str] = Field(
        default_factory=list,
        description="Chunk ids rejected as weak, duplicate, or irrelevant.",
    )
    missing_information: list[str] = Field(
        default_factory=list,
        description="Known information gaps that remain unresolved.",
    )
    contradictions_found: list[str] = Field(
        default_factory=list,
        description="Contradictions found across retrieved evidence.",
    )
    evidence_summary: str = Field(
        default="",
        description="Concise summary of what the retained evidence supports.",
    )
    recommended_action: RecommendedAction = Field(
        default="proceed_with_caveats",
        description="Whether to proceed, proceed with caveats, or retrieve more.",
    )
    notes_for_drafting: list[str] = Field(
        default_factory=list,
        description="Instructions/caveats to carry into answer drafting.",
    )
    coverage_by_sub_question: dict[str, CoverageLevel] = Field(
        default_factory=dict,
        description="Coverage strength per planner sub-question.",
    )
    num_supporting_chunks: int = Field(
        default=0,
        ge=0,
        description="Number of chunks considered supportive.",
    )
    num_example_chunks: int = Field(
        default=0,
        ge=0,
        description="Number of selected chunks that contain example-like content.",
    )
