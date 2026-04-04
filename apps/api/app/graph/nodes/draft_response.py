"""Drafting and polishing node implementations."""

from __future__ import annotations

import logging
import uuid
from typing import Literal

from app.db.models import RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState
from app.services.drafting import draft_answer, polish_answer
from app.services.evidence_analysis import active_evidence, evidence_item_key
from app.services.finalization import append_answer_version

logger = logging.getLogger(__name__)


async def draft_response_node(nodes, state: WorkflowState) -> WorkflowState:
    """Draft investor-grade response grounded in evidence."""

    async def _operation() -> WorkflowState:
        selected_evidence = state.get("selected_evidence", []) or state.get("curated_evidence", [])
        logger.debug(
            "Node draft_response started session_id=%s evidence_count=%d",
            state.get("session_id"),
            len(selected_evidence),
        )
        answer, draft_confidence_notes, draft_confidence_payload, draft_metadata = await draft_answer(
            question=state["question_text"],
            question_type=state.get("question_type", "other"),
            tone=state.get("tone", "formal"),
            evidence=selected_evidence,
            existing_confidence=state.get("confidence_notes", ""),
            synthesis=state.get("evidence_synthesis", {}),
            retrieval_plan=state.get("retrieval_plan", {}),
            evidence_evaluation=state.get("evidence_evaluation", {}),
            retrieval_strategy_used=state.get("retrieval_strategy_used"),
        )
        base_confidence_payload = dict(state.get("confidence_payload", {}) or {})
        confidence_payload = base_confidence_payload or draft_confidence_payload
        confidence_payload = {
            **confidence_payload,
            "draft_metadata": draft_metadata,
        }
        confidence_notes = str(state.get("confidence_notes", "")).strip() or draft_confidence_notes
        logger.info(
            "Node draft_response completed session_id=%s answer_chars=%d",
            state.get("session_id"),
            len(answer),
        )

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                session.draft_answer = answer
                session.confidence_notes = confidence_notes
                session.confidence_payload = confidence_payload
                session.selected_evidence_payload = selected_evidence
                session.evidence_gaps_acknowledged = False
                session.evidence_gaps_acknowledged_at = None
                session.status = "awaiting_review"
                await db.commit()

        return {
            "draft_answer": answer,
            "draft_origin": "initial",
            "draft_metadata": draft_metadata,
            "confidence_notes": confidence_notes,
            "confidence_payload": confidence_payload,
            "status": "awaiting_review",
            "current_node": "draft_response",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="draft_response",
        state=state,
        operation=_operation,
    )


async def polish_response_node(nodes, state: WorkflowState) -> WorkflowState:
    """Apply a final tone-polish pass before human review."""

    async def _operation() -> WorkflowState:
        logger.debug("Node polish_response started session_id=%s", state.get("session_id"))
        draft_text = state.get("draft_answer", "")
        evidence_for_snapshot = state.get("curated_evidence", [])
        included_chunk_ids = [
            evidence_item_key(item)
            for item in active_evidence(evidence_for_snapshot)
        ]
        excluded_chunk_ids = [
            evidence_item_key(item)
            for item in evidence_for_snapshot
            if bool(item.get("excluded_by_reviewer", False))
        ]
        polished_text = await polish_answer(
            question=state.get("question_text", ""),
            question_type=state.get("question_type", "other"),
            tone=state.get("tone", "formal"),
            draft_answer=draft_text,
            evidence=active_evidence(evidence_for_snapshot),
        )
        stage: Literal["draft", "revision"] = "revision" if state.get("draft_origin") == "revision" else "draft"
        logger.info(
            "Node polish_response completed session_id=%s original_chars=%d polished_chars=%d stage=%s",
            state.get("session_id"),
            len(draft_text),
            len(polished_text),
            stage,
        )

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                next_versions = append_answer_version(
                    list(getattr(session, "answer_versions_payload", []) or []),
                    polished_text,
                    stage,
                    question_type=state.get("question_type"),
                    confidence_notes=state.get("confidence_notes", ""),
                    confidence_payload=state.get("confidence_payload", {}),
                    revision_feedback=state.get("review_comments", "") if stage == "revision" else "",
                    included_chunk_ids=included_chunk_ids,
                    excluded_chunk_ids=excluded_chunk_ids,
                )
                session.draft_answer = polished_text
                session.answer_versions_payload = next_versions
                await db.commit()

        return {
            "draft_answer": polished_text,
            "answer_versions": append_answer_version(
                state.get("answer_versions", []),
                polished_text,
                stage,
                question_type=state.get("question_type"),
                confidence_notes=state.get("confidence_notes", ""),
                confidence_payload=state.get("confidence_payload", {}),
                revision_feedback=state.get("review_comments", "") if stage == "revision" else "",
                included_chunk_ids=included_chunk_ids,
                excluded_chunk_ids=excluded_chunk_ids,
            ),
            "current_node": "polish_response",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="polish_response",
        state=state,
        operation=_operation,
    )
