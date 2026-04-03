"""Graph execution helpers with run-level observability instrumentation."""

from __future__ import annotations

import logging

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.types import Command

from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.graph.nodes import WorkflowNodes
from app.graph.workflow import build_workflow
from app.services.observability import (
    create_graph_run,
    determine_graph_status,
    finalize_graph_run,
    refresh_session_metrics,
    reset_observability_context,
    set_observability_context,
)

logger = logging.getLogger(__name__)

GRAPH_NAME = "respondai_rfp_workflow"


def _build_graph(checkpointer):
    logger.debug("Building workflow graph")
    nodes = WorkflowNodes(AsyncSessionLocal)
    return build_workflow(nodes=nodes, checkpointer=checkpointer)


def _checkpointer_conn_string() -> str:
    """Return PostgresSaver-compatible connection string from `DATABASE_URL`."""

    return settings.database_url.replace("+psycopg", "")


async def run_until_human_review(payload: dict, thread_id: str) -> dict:
    """Run workflow from start until the human-review interrupt is reached."""

    logger.info("Running workflow to review pause thread_id=%s", thread_id)
    graph_run_id = await create_graph_run(
        graph_name=GRAPH_NAME,
        thread_id=thread_id,
        session_id=str(payload.get("session_id", "") or "") or None,
        metadata={"entrypoint": "run_until_human_review"},
    )

    context_token = set_observability_context(
        graph_run_id=str(graph_run_id) if graph_run_id else None,
        graph_name=GRAPH_NAME,
        session_id=str(payload.get("session_id", "") or "") or None,
    )

    result: dict | None = None
    session_id_for_metrics: str | None = None

    try:
        async with AsyncPostgresSaver.from_conn_string(_checkpointer_conn_string()) as checkpointer:
            await checkpointer.setup()
            graph = _build_graph(checkpointer)
            result = await graph.ainvoke(payload, config={"configurable": {"thread_id": thread_id}})
            logger.info("Workflow run completed to review pause thread_id=%s", thread_id)
            if isinstance(result, dict):
                session_id_for_metrics = str(result.get("session_id", "") or "") or None

            await finalize_graph_run(
                graph_run_id,
                status=determine_graph_status(result, default_status="paused_for_review"),
                session_id=session_id_for_metrics,
                metadata={"entrypoint": "run_until_human_review"},
            )
            if session_id_for_metrics:
                await refresh_session_metrics(session_id_for_metrics)
            return result
    except Exception as exc:
        await finalize_graph_run(
            graph_run_id,
            status="error",
            session_id=session_id_for_metrics,
            metadata={"entrypoint": "run_until_human_review"},
            error_message=str(exc),
        )
        raise
    finally:
        reset_observability_context(context_token)


async def resume_from_review(thread_id: str, review_payload: dict) -> dict:
    """Resume a previously interrupted workflow with human feedback."""

    logger.info("Resuming workflow from review thread_id=%s", thread_id)
    graph_run_id = await create_graph_run(
        graph_name=GRAPH_NAME,
        thread_id=thread_id,
        session_id=str(review_payload.get("session_id", "") or "") or None,
        metadata={"entrypoint": "resume_from_review"},
    )

    context_token = set_observability_context(
        graph_run_id=str(graph_run_id) if graph_run_id else None,
        graph_name=GRAPH_NAME,
        session_id=str(review_payload.get("session_id", "") or "") or None,
    )

    result: dict | None = None
    session_id_for_metrics = str(review_payload.get("session_id", "") or "") or None

    try:
        async with AsyncPostgresSaver.from_conn_string(_checkpointer_conn_string()) as checkpointer:
            await checkpointer.setup()
            graph = _build_graph(checkpointer)
            result = await graph.ainvoke(
                Command(resume=review_payload),
                config={"configurable": {"thread_id": thread_id}},
            )
            logger.info("Workflow resume completed thread_id=%s", thread_id)

            if isinstance(result, dict):
                session_id_for_metrics = str(result.get("session_id", "") or "") or session_id_for_metrics

            await finalize_graph_run(
                graph_run_id,
                status=determine_graph_status(result, default_status="completed"),
                session_id=session_id_for_metrics,
                metadata={"entrypoint": "resume_from_review"},
            )
            if session_id_for_metrics:
                await refresh_session_metrics(session_id_for_metrics)
            return result
    except Exception as exc:
        await finalize_graph_run(
            graph_run_id,
            status="error",
            session_id=session_id_for_metrics,
            metadata={"entrypoint": "resume_from_review"},
            error_message=str(exc),
        )
        raise
    finally:
        reset_observability_context(context_token)
