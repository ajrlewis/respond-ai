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
