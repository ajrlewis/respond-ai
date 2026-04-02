"""Conditional routing helpers for the LangGraph workflow."""

import logging

from app.graph.state import WorkflowState

logger = logging.getLogger(__name__)


def route_review(state: WorkflowState) -> str:
    """Route based on human reviewer action."""

    action = state.get("review_action")
    logger.debug("Routing review action=%s", action)
    if action == "approve":
        return "approve"
    if action == "revise":
        return "revise"
    logger.warning("Unexpected review action=%s, defaulting to revise", action)
    return "revise"


def route_evidence_evaluation(state: WorkflowState) -> str:
    """Route based on evaluator recommendation with bounded retry."""

    evaluation = state.get("evidence_evaluation", {})
    action = str((evaluation or {}).get("recommended_action", "")).strip()
    retry_count = int(state.get("retry_count", 0) or 0)
    logger.debug("Routing evidence evaluation action=%s retry_count=%d", action, retry_count)

    if action == "retrieve_more" and retry_count < 1:
        return "retrieve_more"
    return "proceed"
