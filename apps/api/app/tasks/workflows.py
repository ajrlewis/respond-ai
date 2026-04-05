"""Celery tasks for background workflow execution."""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from app.core.celery_app import celery_app
from app.core.database import AsyncSessionLocal
from app.graph.runtime import resume_from_review, run_until_human_review
from app.services.session_service import SessionService
from app.services.workflow_events import workflow_event_bus

logger = logging.getLogger(__name__)


async def _load_session_id_by_thread(thread_id: str) -> str | None:
    async with AsyncSessionLocal() as db:
        session = await SessionService(db).get_session_by_thread_id(thread_id)
        return str(session.id) if session else None


async def _run_ask_workflow_async(
    *,
    thread_id: str,
    question_text: str,
    tone: str,
    session_id: str | None,
) -> None:
    logger.info("Background ask workflow started thread_id=%s session_id=%s", thread_id, session_id)
    await workflow_event_bus.publish_thread(thread_id=thread_id, reason="workflow_started")
    await workflow_event_bus.publish_session(
        session_id=session_id,
        thread_id=thread_id,
        reason="workflow_started",
        status="running",
    )

    try:
        result = await run_until_human_review(
            {
                "thread_id": thread_id,
                "question_text": question_text,
                "tone": tone,
                "session_id": session_id,
            },
            thread_id=thread_id,
        )
        resolved_session_id = str(result.get("session_id", "") or "") or session_id or await _load_session_id_by_thread(thread_id)
        if resolved_session_id:
            await workflow_event_bus.register_thread_session(thread_id=thread_id, session_id=resolved_session_id)
            await workflow_event_bus.publish_session(
                session_id=resolved_session_id,
                thread_id=thread_id,
                reason="workflow_paused_for_review",
                status=str(result.get("status", "") or "") or "awaiting_review",
            )
        logger.info("Background ask workflow paused for review thread_id=%s session_id=%s", thread_id, resolved_session_id)
    except Exception as exc:
        resolved_session_id = session_id or await _load_session_id_by_thread(thread_id)
        await workflow_event_bus.publish_thread(
            thread_id=thread_id,
            reason="workflow_error",
            error=str(exc),
        )
        await workflow_event_bus.publish_session(
            session_id=resolved_session_id,
            thread_id=thread_id,
            reason="workflow_error",
            status="error",
            error=str(exc),
        )
        logger.exception("Background ask workflow failed thread_id=%s session_id=%s", thread_id, resolved_session_id)
        raise


async def _run_review_workflow_async(*, thread_id: str, review_payload: dict[str, Any]) -> None:
    session_id = str(review_payload.get("session_id", "") or "") or None
    action = str(review_payload.get("reviewer_action", "") or "").strip().lower()
    started_reason = "revision_started" if action == "revise" else "finalization_started"
    logger.info(
        "Background review workflow started thread_id=%s session_id=%s action=%s",
        thread_id,
        session_id,
        action,
    )
    await workflow_event_bus.publish_session(
        session_id=session_id,
        thread_id=thread_id,
        reason=started_reason,
        status="running",
    )
    await workflow_event_bus.publish_thread(thread_id=thread_id, reason=started_reason)

    try:
        result = await resume_from_review(thread_id=thread_id, review_payload=review_payload)
        resolved_session_id = str(result.get("session_id", "") or "") or session_id or await _load_session_id_by_thread(thread_id)
        await workflow_event_bus.publish_session(
            session_id=resolved_session_id,
            thread_id=thread_id,
            reason="workflow_completed",
            status=str(result.get("status", "") or "") or None,
        )
        logger.info(
            "Background review workflow completed thread_id=%s session_id=%s status=%s",
            thread_id,
            resolved_session_id,
            result.get("status"),
        )
    except Exception as exc:
        await workflow_event_bus.publish_session(
            session_id=session_id,
            thread_id=thread_id,
            reason="workflow_error",
            status="error",
            error=str(exc),
        )
        await workflow_event_bus.publish_thread(
            thread_id=thread_id,
            reason="workflow_error",
            error=str(exc),
        )
        logger.exception("Background review workflow failed thread_id=%s session_id=%s", thread_id, session_id)
        raise


@celery_app.task(name="workflows.run_ask")
def run_ask_workflow_task(
    *,
    thread_id: str,
    question_text: str,
    tone: str,
    session_id: str | None = None,
) -> None:
    """Execute ask workflow asynchronously via Celery worker."""

    asyncio.run(
        _run_ask_workflow_async(
            thread_id=thread_id,
            question_text=question_text,
            tone=tone,
            session_id=session_id,
        )
    )


@celery_app.task(name="workflows.run_review_resume")
def run_review_workflow_task(*, thread_id: str, review_payload: dict[str, Any]) -> None:
    """Resume workflow after review asynchronously via Celery worker."""

    asyncio.run(_run_review_workflow_async(thread_id=thread_id, review_payload=review_payload))


def enqueue_ask_workflow(*, thread_id: str, question_text: str, tone: str, session_id: str | None) -> str:
    """Dispatch ask workflow task and return Celery task id."""

    result = run_ask_workflow_task.delay(
        thread_id=thread_id,
        question_text=question_text,
        tone=tone,
        session_id=session_id,
    )
    return str(result.id)


def enqueue_review_workflow(*, thread_id: str, review_payload: dict[str, Any]) -> str:
    """Dispatch review-resume workflow task and return Celery task id."""

    result = run_review_workflow_task.delay(thread_id=thread_id, review_payload=review_payload)
    return str(result.id)
