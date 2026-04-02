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
