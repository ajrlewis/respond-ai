"""Classify-and-plan node implementation."""

from __future__ import annotations

import logging
import uuid

from app.db.models import RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState
from app.services.planning import classification_from_plan, plan_retrieval

logger = logging.getLogger(__name__)


async def classify_and_plan_node(nodes, state: WorkflowState) -> WorkflowState:
    """Classify question and produce a structured retrieval plan."""

    async def _operation() -> WorkflowState:
        question_text = state["question_text"]
        logger.debug(
            "Node classify_and_plan started session_id=%s question_chars=%d",
            state.get("session_id"),
            len(question_text),
        )
        plan = await plan_retrieval(question_text)
        logger.info(
            "Node classify_and_plan completed session_id=%s category=%s strategy=%s sub_questions=%d",
            state.get("session_id"),
            plan.question_type,
            plan.retrieval_strategy,
            len(plan.sub_questions),
        )

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                session.question_type = plan.question_type
                session.retrieval_plan_payload = plan.model_dump()
                session.retrieval_strategy_used = plan.retrieval_strategy
                session.retry_count = int(state.get("retry_count", 0) or 0)
                await db.commit()

        classification = classification_from_plan(plan)
        return {
            "question_type": plan.question_type,
            "classification": classification.model_dump(),
            "retrieval_plan": plan.model_dump(),
            "retry_count": int(state.get("retry_count", 0) or 0),
            "current_node": "classify_and_plan",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="classify_and_plan",
        state=state,
        operation=_operation,
    )
