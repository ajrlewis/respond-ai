"""Session evaluators that score quality and process outcomes from persisted artefacts."""

from __future__ import annotations

from dataclasses import dataclass

from app.evals.metrics import (
    MetricResult,
    clamp_score,
    score_cost_efficiency,
    score_evidence_readiness,
    score_grounding,
    score_latency,
    score_planning_quality,
    score_retrieval_efficiency,
    score_review_process,
)


@dataclass(slots=True)
class SessionEvalInput:
    """Normalized record used by evaluators."""

    session_id: str
    approved: bool
    has_final_answer: bool
    num_retrieved_chunks: int
    num_cited_chunks: int
    num_revision_rounds: int
    review_event_count: int
    time_to_first_draft_ms: int | None
    time_to_approval_ms: int | None
    total_tokens: int
    estimated_cost_usd: float | None
    has_retrieval_plan: bool
    planner_sub_question_count: int
    retrieval_strategy_used: str | None
    evidence_coverage: str | None
    recommended_action: str | None
    missing_information_count: int
    retrieval_retry_count: int


@dataclass(slots=True)
class SessionEvalScore:
    """Aggregated evaluation score for one session."""

    session_id: str
    overall_score: float
    passed: bool
    metrics: list[MetricResult]


def evaluate_session(record: SessionEvalInput) -> SessionEvalScore:
    """Compute metric-level and overall score for one session."""

    metrics = [
        score_grounding(
            num_cited_chunks=record.num_cited_chunks,
            num_retrieved_chunks=record.num_retrieved_chunks,
            has_final_answer=record.has_final_answer,
        ),
        score_retrieval_efficiency(
            num_cited_chunks=record.num_cited_chunks,
            num_retrieved_chunks=record.num_retrieved_chunks,
        ),
        score_review_process(
            approved=record.approved,
            num_revision_rounds=record.num_revision_rounds,
            review_event_count=record.review_event_count,
        ),
        score_planning_quality(
            has_retrieval_plan=record.has_retrieval_plan,
            planner_sub_question_count=record.planner_sub_question_count,
            retrieval_strategy_used=record.retrieval_strategy_used,
        ),
        score_evidence_readiness(
            evidence_coverage=record.evidence_coverage,
            recommended_action=record.recommended_action,
            missing_information_count=record.missing_information_count,
            retrieval_retry_count=record.retrieval_retry_count,
            has_final_answer=record.has_final_answer,
        ),
        score_latency(
            time_to_first_draft_ms=record.time_to_first_draft_ms,
            time_to_approval_ms=record.time_to_approval_ms,
        ),
        score_cost_efficiency(
            total_tokens=record.total_tokens,
            estimated_cost_usd=record.estimated_cost_usd,
        ),
    ]

    overall = clamp_score(sum(metric.score for metric in metrics) / len(metrics)) if metrics else 0.0
    passed = all(metric.passed for metric in metrics)
    return SessionEvalScore(
        session_id=record.session_id,
        overall_score=overall,
        passed=passed,
        metrics=metrics,
    )
