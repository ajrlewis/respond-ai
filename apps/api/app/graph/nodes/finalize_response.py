"""Finalization node implementation."""

from __future__ import annotations

from datetime import UTC, datetime
import logging
import uuid

from sqlalchemy import select

from app.db.models import RFPReview, RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState
from app.services.finalization import build_finalization_artifacts

logger = logging.getLogger(__name__)


async def finalize_response_node(nodes, state: WorkflowState) -> WorkflowState:
    """Persist final approved answer."""

    async def _operation() -> WorkflowState:
        logger.info(
            "Node finalize_response started session_id=%s has_edited_answer=%s",
            state.get("session_id"),
            bool(state.get("edited_answer")),
        )
        approved_at = datetime.now(UTC)
        final_answer = ""
        final_version_number: int | None = None

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                review_rows = list(
                    (
                        await db.execute(
                            select(RFPReview)
                            .where(RFPReview.session_id == session.id)
                            .order_by(RFPReview.created_at.asc())
                        )
                    )
                    .scalars()
                    .all()
                )
                artifacts = build_finalization_artifacts(
                    session=session,
                    state=state,
                    review_rows=review_rows,
                    approved_at=approved_at,
                )
                final_answer = artifacts.final_answer
                final_version_number = artifacts.final_version_number

                session.final_answer = artifacts.final_answer
                session.final_version_number = artifacts.final_version_number
                session.approved_at = approved_at
                session.reviewer_action = "approve"
                session.reviewer_id = artifacts.reviewer_id
                session.answer_versions_payload = artifacts.next_versions
                session.final_audit_payload = artifacts.final_audit_payload
                session.status = "approved"
                await db.commit()
                logger.info("Node finalize_response persisted session_id=%s", state.get("session_id"))

        return {
            "final_answer": final_answer,
            "final_version_number": final_version_number,
            "approved_at": approved_at.isoformat(),
            "status": "approved",
            "current_node": "finalize_response",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="finalize_response",
        state=state,
        operation=_operation,
    )
