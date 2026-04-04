"""Revision node implementation."""

from __future__ import annotations

import logging
import uuid

from app.db.models import RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState
from app.services.drafting import revise_answer
from app.services.evidence_analysis import active_evidence, mark_excluded_evidence

logger = logging.getLogger(__name__)


async def revise_response_node(nodes, state: WorkflowState) -> WorkflowState:
    """Revise draft based on reviewer feedback."""

    async def _operation() -> WorkflowState:
        logger.debug(
            "Node revise_response started session_id=%s feedback_chars=%d",
            state.get("session_id"),
            len(state.get("review_comments", "")),
        )
        prior_evidence = state.get("curated_evidence", [])
        requested_exclusions = [
            key.strip()
            for key in state.get("excluded_evidence_keys", [])
            if isinstance(key, str) and key.strip()
        ]
        merged_exclusions = sorted(set(requested_exclusions))
        marked_evidence = mark_excluded_evidence(prior_evidence, merged_exclusions)
        filtered_evidence = active_evidence(marked_evidence)
        retrieval_notes = str((state.get("confidence_payload") or {}).get("retrieval_notes", "")).strip()
        if requested_exclusions:
            retrieval_notes = (
                f"{retrieval_notes} Reviewer excluded {len(requested_exclusions)} chunk(s) for this revision."
            ).strip()

        revised_text, revised_confidence_notes, revised_confidence_payload, revision_intent, draft_metadata = await revise_answer(
            question=state["question_text"],
            question_type=state.get("question_type", "other"),
            prior_draft=state.get("draft_answer", ""),
            evidence=filtered_evidence,
            reviewer_feedback=state.get("review_comments", ""),
            tone=state.get("tone", "formal"),
            retrieval_notes=retrieval_notes,
        )
        base_confidence_payload = dict(state.get("confidence_payload", {}) or {})
        if filtered_evidence and base_confidence_payload:
            confidence_payload = {
                **base_confidence_payload,
                "revision_intent": revision_intent,
                "draft_metadata": draft_metadata,
            }
            confidence_notes = str(state.get("confidence_notes", "")).strip() or revised_confidence_notes
        else:
            confidence_payload = {
                **revised_confidence_payload,
                "revision_intent": revision_intent,
                "draft_metadata": draft_metadata,
            }
            confidence_notes = revised_confidence_notes
        logger.info(
            "Node revise_response completed session_id=%s answer_chars=%d evidence_used=%d evidence_excluded=%d",
            state.get("session_id"),
            len(revised_text),
            len(filtered_evidence),
            len(merged_exclusions),
        )

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                session.draft_answer = revised_text
                session.confidence_notes = confidence_notes
                session.confidence_payload = confidence_payload
                session.evidence_payload = marked_evidence
                session.evidence_gaps_acknowledged = False
                session.evidence_gaps_acknowledged_at = None
                session.status = "awaiting_review"
                await db.commit()

        return {
            "draft_answer": revised_text,
            "draft_origin": "revision",
            "curated_evidence": marked_evidence,
            "revision_intent": revision_intent,
            "draft_metadata": draft_metadata,
            "confidence_notes": confidence_notes,
            "confidence_payload": confidence_payload,
            "status": "awaiting_review",
            "excluded_evidence_keys": merged_exclusions,
            "review_action": "",
            "current_node": "revise_response",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="revise_response",
        state=state,
        operation=_operation,
    )
