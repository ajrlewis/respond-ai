"""Shared metric primitives for offline session evaluations."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class MetricResult:
    """Single metric score with pass/fail outcome and structured detail."""

    name: str
    score: float
    passed: bool
    details: dict


def clamp_score(value: float) -> float:
    """Clamp score to [0, 1] for consistent reporting."""

    if value < 0:
        return 0.0
    if value > 1:
        return 1.0
    return round(value, 4)


def ratio(numerator: int, denominator: int) -> float:
    """Safe ratio helper that returns zero when denominator is not positive."""

    if denominator <= 0:
        return 0.0
    return numerator / denominator


def score_grounding(*, num_cited_chunks: int, num_retrieved_chunks: int, has_final_answer: bool) -> MetricResult:
    """Score whether response appears grounded in retrieved evidence."""

    citation_ratio = ratio(num_cited_chunks, max(1, num_retrieved_chunks))
    base = citation_ratio if has_final_answer else citation_ratio * 0.6
    passed = has_final_answer and num_cited_chunks > 0 and base >= 0.25
    return MetricResult(
        name="grounding",
        score=clamp_score(base),
        passed=passed,
        details={
            "has_final_answer": has_final_answer,
            "num_cited_chunks": num_cited_chunks,
            "num_retrieved_chunks": num_retrieved_chunks,
            "citation_ratio": round(citation_ratio, 4),
        },
    )


def score_retrieval_efficiency(*, num_cited_chunks: int, num_retrieved_chunks: int) -> MetricResult:
    """Score evidence selectivity and retrieval quality."""

    efficiency = ratio(num_cited_chunks, max(1, num_retrieved_chunks))
    passed = efficiency >= 0.2 or num_retrieved_chunks == 0
    return MetricResult(
        name="retrieval_efficiency",
        score=clamp_score(efficiency),
        passed=passed,
        details={
            "num_cited_chunks": num_cited_chunks,
            "num_retrieved_chunks": num_retrieved_chunks,
            "efficiency": round(efficiency, 4),
        },
    )


def score_review_process(*, approved: bool, num_revision_rounds: int, review_event_count: int) -> MetricResult:
    """Score whether workflow includes explicit review and approval controls."""

    has_review = review_event_count > 0
    revision_bonus = min(0.2, num_revision_rounds * 0.05)
    base = (0.8 if approved else 0.5) + (0.2 if has_review else 0.0) + revision_bonus
    score = clamp_score(base)
    passed = approved and has_review
    return MetricResult(
        name="review_process",
        score=score,
        passed=passed,
        details={
            "approved": approved,
            "review_event_count": review_event_count,
            "num_revision_rounds": num_revision_rounds,
        },
    )


def score_latency(*, time_to_first_draft_ms: int | None, time_to_approval_ms: int | None) -> MetricResult:
    """Score operational latency using simple enterprise-friendly thresholds."""

    first_draft_score = 0.5
    if time_to_first_draft_ms is not None:
        if time_to_first_draft_ms <= 30_000:
            first_draft_score = 1.0
        elif time_to_first_draft_ms <= 120_000:
            first_draft_score = 0.75
        else:
            first_draft_score = 0.5

    approval_score = 0.5
    if time_to_approval_ms is not None:
        if time_to_approval_ms <= 15 * 60_000:
            approval_score = 1.0
        elif time_to_approval_ms <= 60 * 60_000:
            approval_score = 0.75
        else:
            approval_score = 0.5

    score = clamp_score((first_draft_score + approval_score) / 2)
    passed = score >= 0.6
    return MetricResult(
        name="latency",
        score=score,
        passed=passed,
        details={
            "time_to_first_draft_ms": time_to_first_draft_ms,
            "time_to_approval_ms": time_to_approval_ms,
        },
    )


def score_cost_efficiency(*, total_tokens: int, estimated_cost_usd: float | None) -> MetricResult:
    """Score token/cost utilization with conservative thresholding."""

    if estimated_cost_usd is None:
        return MetricResult(
            name="cost_efficiency",
            score=0.5,
            passed=True,
            details={"reason": "cost unavailable", "total_tokens": total_tokens},
        )

    if estimated_cost_usd <= 0.02:
        score = 1.0
    elif estimated_cost_usd <= 0.08:
        score = 0.75
    elif estimated_cost_usd <= 0.2:
        score = 0.5
    else:
        score = 0.25

    return MetricResult(
        name="cost_efficiency",
        score=clamp_score(score),
        passed=score >= 0.5,
        details={
            "estimated_cost_usd": round(float(estimated_cost_usd), 6),
            "total_tokens": total_tokens,
        },
    )


def score_planning_quality(
    *,
    has_retrieval_plan: bool,
    planner_sub_question_count: int,
    retrieval_strategy_used: str | None,
) -> MetricResult:
    """Score whether structured pre-retrieval planning artifacts were produced."""

    strategy = (retrieval_strategy_used or "").strip().lower()
    has_strategy = strategy in {"semantic", "keyword", "hybrid"}
    base = 0.15
    if has_retrieval_plan:
        base += 0.55
    if planner_sub_question_count > 0:
        base += min(0.2, planner_sub_question_count * 0.05)
    if has_strategy:
        base += 0.1

    score = clamp_score(base)
    passed = has_retrieval_plan and planner_sub_question_count > 0 and has_strategy
    return MetricResult(
        name="planning_quality",
        score=score,
        passed=passed,
        details={
            "has_retrieval_plan": has_retrieval_plan,
            "planner_sub_question_count": planner_sub_question_count,
            "retrieval_strategy_used": retrieval_strategy_used,
        },
    )


def score_evidence_readiness(
    *,
    evidence_coverage: str | None,
    recommended_action: str | None,
    missing_information_count: int,
    retrieval_retry_count: int,
    has_final_answer: bool,
) -> MetricResult:
    """Score whether evidence evaluation outcomes were handled in a controlled way."""

    coverage = (evidence_coverage or "").strip().lower()
    action = (recommended_action or "").strip().lower()
    coverage_score = {"strong": 1.0, "partial": 0.7, "weak": 0.3}.get(coverage, 0.45)

    penalty = min(0.2, max(0, missing_information_count) * 0.04)
    if action == "retrieve_more" and has_final_answer:
        penalty += 0.1

    retry_bonus = 0.05 if retrieval_retry_count > 0 and coverage in {"strong", "partial"} else 0.0
    score = clamp_score(coverage_score - penalty + retry_bonus)

    passed = coverage in {"strong", "partial"} and action in {"proceed", "proceed_with_caveats"}
    return MetricResult(
        name="evidence_readiness",
        score=score,
        passed=passed,
        details={
            "coverage": evidence_coverage,
            "recommended_action": recommended_action,
            "missing_information_count": missing_information_count,
            "retrieval_retry_count": retrieval_retry_count,
            "has_final_answer": has_final_answer,
        },
    )
