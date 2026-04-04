"""Ask node implementation."""

from __future__ import annotations

import logging
import uuid

from sqlalchemy import select

from app.db.models import RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState
from app.services.workflow_events import workflow_event_bus

logger = logging.getLogger(__name__)


async def ask_node(nodes, state: WorkflowState) -> WorkflowState:
    """Create a business session and initialize workflow state."""

    async def _operation() -> WorkflowState:
        thread_id = state.get("thread_id") or str(uuid.uuid4())
        question_text = state["question_text"].strip()
        tone = state.get("tone", "formal")
        logger.info(
            "Node ask started thread_id=%s tone=%s question_chars=%d",
            thread_id,
            tone,
            len(question_text),
        )

        async with nodes._db() as db:
            existing = (
                await db.execute(select(RFPSession).where(RFPSession.graph_thread_id == thread_id))
            ).scalar_one_or_none()
            if existing:
                existing.current_node = "ask"
                await db.commit()
                await workflow_event_bus.register_thread_session(
                    thread_id=thread_id,
                    session_id=str(existing.id),
                )
                logger.info("Node ask reused existing session session_id=%s thread_id=%s", existing.id, thread_id)
                return {
                    "thread_id": thread_id,
                    "session_id": str(existing.id),
                    "status": existing.status,
                    "tone": existing.tone,
                    "current_node": "ask",
                }

            session = RFPSession(
                graph_thread_id=thread_id,
                question_text=question_text,
                tone=tone,
                status="draft",
                current_node="ask",
            )
            db.add(session)
            await db.commit()
            await db.refresh(session)
            await workflow_event_bus.register_thread_session(
                thread_id=thread_id,
                session_id=str(session.id),
            )
            logger.info("Node ask created session session_id=%s thread_id=%s", session.id, thread_id)
            return {
                "thread_id": thread_id,
                "session_id": str(session.id),
                "status": session.status,
                "tone": session.tone,
                "current_node": "ask",
            }

    return await execute_node(
        nodes=nodes,
        node_name="ask",
        state=state,
        operation=_operation,
        set_current_node=False,
    )
