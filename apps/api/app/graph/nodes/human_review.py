"""Human review interrupt node implementation."""

from __future__ import annotations

import logging
import uuid

from langgraph.types import interrupt

from app.db.models import RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState

logger = logging.getLogger(__name__)


async def human_review_node(nodes, state: WorkflowState) -> WorkflowState:
    """Pause graph for human review and resume with action payload."""

    async def _operation() -> WorkflowState:
        logger.info("Node human_review interrupting session_id=%s", state.get("session_id"))
        review_payload = interrupt(
            {
                "session_id": state["session_id"],
                "question_text": state["question_text"],
                "draft_answer": state.get("draft_answer", ""),
                "confidence_notes": state.get("confidence_notes", ""),
                "confidence_payload": state.get("confidence_payload", {}),
                "evidence": state.get("curated_evidence", []),
                "answer_versions": state.get("answer_versions", []),
            }
        )

        review_action = review_payload.get("reviewer_action", "revise")
        reviewer_id = str(review_payload.get("reviewer_id", "")).strip()
        review_comments = review_payload.get("review_comments", "")
        edited_answer = review_payload.get("edited_answer", "")
        excluded_evidence_keys = [
            key.strip() for key in review_payload.get("excluded_evidence_keys", []) if isinstance(key, str) and key.strip()
        ]
        reviewed_evidence_gaps = bool(review_payload.get("reviewed_evidence_gaps", False))
        logger.info(
            "Node human_review resumed session_id=%s action=%s comments_chars=%d edited_chars=%d excluded=%d",
            state.get("session_id"),
            review_action,
            len(review_comments),
            len(edited_answer),
            len(excluded_evidence_keys),
        )

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                session.status = "revision_requested" if review_action == "revise" else "awaiting_finalization"
                await db.commit()

        return {
            "review_action": review_action,
            "reviewer_id": reviewer_id,
            "review_comments": review_comments,
            "edited_answer": edited_answer,
            "excluded_evidence_keys": excluded_evidence_keys,
            "reviewed_evidence_gaps": reviewed_evidence_gaps,
            "current_node": "human_review",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="human_review",
        state=state,
        operation=_operation,
    )
