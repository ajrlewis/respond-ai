"""Planning services for question classification and retrieval planning."""

from __future__ import annotations

import logging

from app.ai import get_structured_model
from app.ai.schemas import QuestionClassificationResult, RetrievalPlanResult
from app.prompts import render_prompt_template

logger = logging.getLogger(__name__)

async def plan_retrieval(question_text: str) -> RetrievalPlanResult:
    """Produce retrieval plan via structured model."""

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


def classification_from_plan(plan: RetrievalPlanResult) -> QuestionClassificationResult:
    """Build legacy-compatible classification payload from retrieval plan."""

    return QuestionClassificationResult(
        question_type=plan.question_type,
        reasoning_summary=plan.reasoning_summary,
        suggested_retrieval_strategy=plan.retrieval_strategy,
        confidence=plan.confidence,
    )
