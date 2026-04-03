"""Planning services for question classification and retrieval planning."""

from __future__ import annotations

import logging

from app.ai import AIConfigurationError, AIProviderError, get_structured_model
from app.ai.schemas import QuestionClassificationResult, RetrievalPlanResult
from app.core.config import settings
from app.prompts import render_prompt_template

logger = logging.getLogger(__name__)


def retrieval_plan_fallback(question_text: str) -> RetrievalPlanResult:
    """Deterministic fallback plan when structured planner is unavailable."""

    lowered = question_text.lower()
    if "esg" in lowered or "sustainability" in lowered:
        category = "esg"
    elif "risk" in lowered or "regulator" in lowered or "policy" in lowered:
        category = "risk"
    elif "team" in lowered:
        category = "team"
    elif "different" in lowered or "edge" in lowered:
        category = "differentiation"
    elif "track record" in lowered or "example" in lowered:
        category = "track_record"
    elif "process" in lowered or "due diligence" in lowered or "operat" in lowered:
        category = "operations"
    elif "strategy" in lowered or "renewable" in lowered:
        category = "strategy"
    else:
        category = "other"

    needs_examples = any(token in lowered for token in ("example", "case", "track record", "value creation"))
    needs_quantitative_support = any(
        token in lowered for token in ("return", "performance", "kpi", "capacity", "mw", "%", "metric")
    )
    needs_regulatory_context = any(token in lowered for token in ("regulator", "sfdr", "policy", "compliance"))

    priority_sources = [category]
    if needs_examples:
        priority_sources.append("portfolio_examples")
    if needs_quantitative_support:
        priority_sources.append("performance_metrics")
    if needs_regulatory_context:
        priority_sources.append("regulatory_policy")

    return RetrievalPlanResult(
        question_type=category,
        reasoning_summary="Heuristic planning fallback applied because structured planner was unavailable.",
        sub_questions=[
            "What direct evidence answers the core question?",
            "What supporting examples demonstrate outcomes?",
            "What caveats or gaps remain based on available internal documents?",
        ],
        retrieval_strategy="hybrid",
        priority_sources=priority_sources,
        needs_examples=needs_examples,
        needs_quantitative_support=needs_quantitative_support,
        should_expand_context=needs_examples or needs_quantitative_support or needs_regulatory_context,
        needs_regulatory_context=needs_regulatory_context,
        needs_prior_answers=True,
        preferred_top_k=min(18, max(8, settings.retrieval_top_k)),
        confidence=0.45,
    )


async def plan_retrieval(question_text: str) -> RetrievalPlanResult:
    """Produce retrieval plan via structured model with deterministic fallback."""

    try:
        planner = get_structured_model(
            schema=RetrievalPlanResult,
            purpose="planning",
        )
        plan = await planner.ainvoke(
            system_prompt=render_prompt_template("classify_and_plan", "system"),
            user_prompt=render_prompt_template("classify_and_plan", "user", question_text=question_text),
            temperature=0,
        )
        logger.debug(
            "Retrieval planning completed via model category=%s strategy=%s",
            plan.question_type,
            plan.retrieval_strategy,
        )
        return plan
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.info("Retrieval planning model unavailable; using heuristic fallback error=%s", exc)
        return retrieval_plan_fallback(question_text)


def classification_from_plan(plan: RetrievalPlanResult) -> QuestionClassificationResult:
    """Build legacy-compatible classification payload from retrieval plan."""

    return QuestionClassificationResult(
        question_type=plan.question_type,
        reasoning_summary=plan.reasoning_summary,
        suggested_retrieval_strategy=plan.retrieval_strategy,
        confidence=plan.confidence,
    )
