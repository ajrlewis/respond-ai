"""Evidence retrieval node implementations."""

from __future__ import annotations

import logging
import uuid

from app.ai.schemas import RetrievalPlanResult
from app.db.models import RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState
from app.services.evidence_analysis import adaptive_retrieve, optional_embedding_service

logger = logging.getLogger(__name__)


async def adaptive_retrieve_node(nodes, state: WorkflowState) -> WorkflowState:
    """Retrieve evidence adaptively based on planner output."""

    async def _operation() -> WorkflowState:
        query = state["question_text"]
        retry_count = int(state.get("retry_count", 0) or 0)
        raw_plan = state.get("retrieval_plan")
        if raw_plan is None:
            raise RuntimeError("Missing retrieval_plan in workflow state before adaptive_retrieve.")
        plan = RetrievalPlanResult.model_validate(raw_plan)
        config = nodes._build_retrieval_config(plan=plan, retry_count=retry_count)
        logger.debug(
            "Node adaptive_retrieve started session_id=%s strategy=%s retry=%d",
            state.get("session_id"),
            config["strategy"],
            retry_count,
        )

        async with nodes._db() as db:
            retrieved, retrieval_debug = await adaptive_retrieve(
                db=db,
                query=query,
                plan=plan,
                retry_count=retry_count,
                embedding_service=optional_embedding_service(),
            )

            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                session.retrieval_strategy_used = str(config["strategy"])
                session.retrieval_metadata_payload = retrieval_debug
                session.retrieval_plan_payload = plan.model_dump()
                await db.commit()

        logger.info(
            "Node adaptive_retrieve completed session_id=%s strategy=%s retrieved=%d",
            state.get("session_id"),
            config["strategy"],
            len(retrieved),
        )
        return {
            "retrieval_plan": plan.model_dump(),
            "retrieval_strategy_used": str(config["strategy"]),
            "retrieval_debug": retrieval_debug,
            "retrieved_chunks": retrieved,
            "retrieved_evidence": retrieved,
            "current_node": "adaptive_retrieve",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="adaptive_retrieve",
        state=state,
        operation=_operation,
    )
