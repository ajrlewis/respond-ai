"""LangGraph node package with thin orchestration adapters."""

from __future__ import annotations

from contextlib import asynccontextmanager
import logging
import uuid
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models import RFPSession
from app.graph.nodes.ask import ask_node
from app.graph.nodes.classify_and_plan import classify_and_plan_node
from app.graph.nodes.draft_response import draft_response_node, polish_response_node
from app.graph.nodes.evaluate_evidence import cross_reference_evidence_node, evaluate_evidence_node
from app.graph.nodes.finalize_response import finalize_response_node
from app.graph.nodes.human_review import human_review_node
from app.graph.nodes.retrieve_evidence import adaptive_retrieve_node
from app.graph.nodes.revise_response import revise_response_node
from app.graph.state import WorkflowState
from app.prompts import render_prompt_template as render_central_prompt_template
from app.services.evidence_analysis import (
    active_evidence,
    build_confidence_notes,
    build_retrieval_config,
    curate_evidence,
    evidence_item_key,
    mark_excluded_evidence,
)
from app.services.finalization import append_answer_version
from app.services.observability import (
    create_node_run,
    finalize_node_run,
    get_observability_context,
    push_node_context,
    reset_observability_context,
    summarize_workflow_state,
)
from app.services.confidence import (
    build_structured_confidence_payload,
    render_confidence_notes,
)

logger = logging.getLogger(__name__)


def render_prompt_template(prompt_name: str, template_name: str, **context: str) -> str:
    """Backwards-compatible wrapper around centralized prompt registry."""

    return render_central_prompt_template(prompt_name, template_name, **context)


class WorkflowNodes:
    """Dependency-aware collection of graph nodes."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession]) -> None:
        self.session_factory = session_factory

    async def _start_node_observation(self, node_name: str, state: WorkflowState) -> tuple[str | None, object | None]:
        context = get_observability_context()
        node_run_id = await create_node_run(
            graph_run_id=context.graph_run_id,
            session_id=state.get("session_id"),
            node_name=node_name,
            input_state_summary=summarize_workflow_state(state),
            metadata={"graph_name": context.graph_name or "respondai_rfp_workflow"},
        )
        context_token = push_node_context(
            session_id=state.get("session_id"),
            node_run_id=str(node_run_id) if node_run_id else None,
            node_name=node_name,
        )
        return str(node_run_id) if node_run_id else None, context_token

    async def _finish_node_observation(
        self,
        *,
        node_run_id: str | None,
        context_token: object | None,
        output_state: WorkflowState | dict,
        status: str,
        error_message: str | None = None,
    ) -> None:
        await finalize_node_run(
            node_run_id=node_run_id,
            status=status,
            output_state_summary=summarize_workflow_state(output_state),
            session_id=str(output_state.get("session_id", "") or "") or None,
            error_message=error_message,
        )
        if context_token is not None:
            reset_observability_context(context_token)

    @staticmethod
    def _is_human_wait_interrupt(exc: BaseException) -> bool:
        return exc.__class__.__name__ == "GraphInterrupt"

    @asynccontextmanager
    async def _db(self) -> AsyncIterator[AsyncSession]:
        async with self.session_factory() as db:
            yield db

    async def _set_current_node(self, session_id: str | None, node_name: str) -> None:
        """Persist node-level progress for UI polling."""

        if not session_id:
            return

        async with self._db() as db:
            session = await db.get(RFPSession, uuid.UUID(session_id))
            if not session:
                logger.warning("Progress update skipped for missing session_id=%s node=%s", session_id, node_name)
                return
            session.current_node = node_name
            await db.commit()

    @staticmethod
    def _build_retrieval_config(*, plan, retry_count: int) -> dict[str, int | str | bool]:
        return build_retrieval_config(plan=plan, retry_count=retry_count)

    async def ask(self, state: WorkflowState) -> WorkflowState:
        return await ask_node(self, state)

    async def classify_and_plan(self, state: WorkflowState) -> WorkflowState:
        return await classify_and_plan_node(self, state)

    async def classify_question(self, state: WorkflowState) -> WorkflowState:
        """Backward-compatible wrapper for legacy node name."""

        return await self.classify_and_plan(state)

    async def adaptive_retrieve(self, state: WorkflowState) -> WorkflowState:
        return await adaptive_retrieve_node(self, state)

    async def evaluate_evidence(self, state: WorkflowState) -> WorkflowState:
        return await evaluate_evidence_node(self, state)

    async def cross_reference_evidence(self, state: WorkflowState) -> WorkflowState:
        """Legacy node retained for backward compatibility/tests."""

        return await cross_reference_evidence_node(self, state)

    async def draft_response(self, state: WorkflowState) -> WorkflowState:
        return await draft_response_node(self, state)

    async def polish_response(self, state: WorkflowState) -> WorkflowState:
        return await polish_response_node(self, state)

    async def human_review(self, state: WorkflowState) -> WorkflowState:
        return await human_review_node(self, state)

    async def revise_response(self, state: WorkflowState) -> WorkflowState:
        return await revise_response_node(self, state)

    async def finalize_response(self, state: WorkflowState) -> WorkflowState:
        return await finalize_response_node(self, state)


__all__ = [
    "WorkflowNodes",
    "active_evidence",
    "append_answer_version",
    "build_confidence_notes",
    "build_structured_confidence_payload",
    "curate_evidence",
    "evidence_item_key",
    "mark_excluded_evidence",
    "render_confidence_notes",
    "render_prompt_template",
]
