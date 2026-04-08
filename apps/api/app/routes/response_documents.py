"""Routes for document-centric drafting and versioning."""

from __future__ import annotations

import logging
import uuid
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.schemas.response_documents import (
    AIReviseRequest,
    AIReviseResponse,
    CompareResponseVersionsOut,
    CreateResponseDocumentRequest,
    GenerateResponseDocumentRequest,
    ResponseDocumentOut,
    ResponseVersionSummaryOut,
    SaveResponseVersionRequest,
)
from app.services.response_documents import ResponseDocumentService
from app.services.workflow_events import format_sse_comment, format_sse_event, workflow_event_bus

router = APIRouter(
    prefix="/api/response-documents",
    tags=["response-documents"],
)
logger = logging.getLogger(__name__)


def _document_workflow_payload(signal) -> dict:
    payload: dict[str, object] = {
        "reason": signal.reason,
        "timestamp": signal.timestamp,
    }
    if signal.node_name is not None:
        payload["node"] = signal.node_name
    if signal.status is not None:
        payload["status"] = signal.status
    if signal.error:
        payload["error"] = signal.error
    if signal.metadata:
        payload["metadata"] = signal.metadata
    return payload


@router.get("/{document_id}/events")
async def stream_response_document_events(
    document_id: UUID,
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> StreamingResponse:
    """Stream response-document workflow updates using SSE."""

    service = ResponseDocumentService(db)
    try:
        await service.get_document(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    async def event_generator():
        async with workflow_event_bus.subscribe_document(str(document_id)) as subscription:
            while True:
                if await request.is_disconnected():
                    break

                signal = await subscription.next_event(timeout=15.0)
                if signal is None:
                    yield format_sse_comment("keepalive")
                    continue

                yield format_sse_event(
                    event=signal.event,
                    data=_document_workflow_payload(signal),
                )

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("", response_model=ResponseDocumentOut)
async def create_response_document(
    payload: CreateResponseDocumentRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseDocumentOut:
    """Create a response document from uploaded source/questions or examples."""

    service = ResponseDocumentService(db)
    return await service.create_document(payload)


@router.post("/sample", response_model=ResponseDocumentOut)
async def create_sample_response_document(
    db: AsyncSession = Depends(get_db),
) -> ResponseDocumentOut:
    """Create a response document prefilled with sample questions."""

    service = ResponseDocumentService(db)
    return await service.create_document(
        CreateResponseDocumentRequest(
            title="Sample Response Draft",
            use_example_questions=True,
            source_filename="sample-questions.md",
        )
    )


@router.get("/{document_id}", response_model=ResponseDocumentOut)
async def get_response_document(
    document_id: UUID,
    selected_version_id: UUID | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
) -> ResponseDocumentOut:
    """Fetch a response document and selected (or latest) version."""

    service = ResponseDocumentService(db)
    try:
        return await service.get_document(document_id, selected_version_id=selected_version_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/generate", response_model=ResponseDocumentOut)
async def generate_response_document(
    document_id: UUID,
    payload: GenerateResponseDocumentRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseDocumentOut:
    """Generate a draft answer for each question and save as a new version."""

    service = ResponseDocumentService(db)
    run_id = (payload.run_id or "").strip() or str(uuid.uuid4())

    async def publish_stage(stage_id: str, stage_label: str, stage_status: str) -> None:
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="stage_update",
            node_name=stage_id,
            status=stage_status,
            metadata={
                "run_id": run_id,
                "operation": "generation",
                "stage_id": stage_id,
                "stage_label": stage_label,
                "stage_status": stage_status,
            },
        )

    await workflow_event_bus.publish_document(
        document_id=str(document_id),
        reason="run_started",
        status="running",
        metadata={"run_id": run_id, "operation": "generation"},
    )
    try:
        response = await service.generate_document(
            document_id,
            tone=payload.tone,
            created_by=payload.created_by,
            progress=publish_stage,
        )
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="run_completed",
            status="done",
            metadata={"run_id": run_id, "operation": "generation"},
        )
        return response
    except LookupError as exc:
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="run_failed",
            status="failed",
            error=str(exc),
            metadata={"run_id": run_id, "operation": "generation"},
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="run_failed",
            status="failed",
            error=str(exc),
            metadata={"run_id": run_id, "operation": "generation"},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{document_id}/versions", response_model=list[ResponseVersionSummaryOut])
async def list_response_document_versions(
    document_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> list[ResponseVersionSummaryOut]:
    """List all saved versions for a response document."""

    service = ResponseDocumentService(db)
    try:
        return await service.list_versions(document_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/versions/{version_id}/approve", response_model=ResponseDocumentOut)
async def approve_response_document_version(
    document_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ResponseDocumentOut:
    """Mark a saved version as the approved/final document version."""

    service = ResponseDocumentService(db)
    try:
        return await service.approve_version(document_id, version_id=version_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.delete("/{document_id}/versions/{version_id}", response_model=ResponseDocumentOut)
async def delete_response_document_version(
    document_id: UUID,
    version_id: UUID,
    db: AsyncSession = Depends(get_db),
) -> ResponseDocumentOut:
    """Delete one saved version and return the updated document payload."""

    service = ResponseDocumentService(db)
    try:
        return await service.delete_version(document_id, version_id=version_id)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/{document_id}/versions", response_model=ResponseDocumentOut)
async def save_response_document_version(
    document_id: UUID,
    payload: SaveResponseVersionRequest,
    db: AsyncSession = Depends(get_db),
) -> ResponseDocumentOut:
    """Save editor content as a new response-document version."""

    service = ResponseDocumentService(db)
    try:
        return await service.save_new_version(document_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{document_id}/compare", response_model=CompareResponseVersionsOut)
async def compare_response_document_versions(
    document_id: UUID,
    left_version_id: UUID = Query(...),
    right_version_id: UUID = Query(...),
    db: AsyncSession = Depends(get_db),
) -> CompareResponseVersionsOut:
    """Compare two response-document versions."""

    service = ResponseDocumentService(db)
    try:
        return await service.compare_versions(
            document_id,
            left_version_id=left_version_id,
            right_version_id=right_version_id,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{document_id}/ai-revise", response_model=AIReviseResponse)
async def ai_revise_response_document(
    document_id: UUID,
    payload: AIReviseRequest,
    db: AsyncSession = Depends(get_db),
) -> AIReviseResponse:
    """Return AI revision suggestions from the selected version."""

    service = ResponseDocumentService(db)
    run_id = (payload.run_id or "").strip() or str(uuid.uuid4())

    async def publish_stage(stage_id: str, stage_label: str, stage_status: str) -> None:
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="stage_update",
            node_name=stage_id,
            status=stage_status,
            metadata={
                "run_id": run_id,
                "operation": "revision",
                "stage_id": stage_id,
                "stage_label": stage_label,
                "stage_status": stage_status,
            },
        )

    await workflow_event_bus.publish_document(
        document_id=str(document_id),
        reason="run_started",
        status="running",
        metadata={"run_id": run_id, "operation": "revision"},
    )
    try:
        response = await service.ai_revise(document_id, payload, progress=publish_stage)
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="run_completed",
            status="done",
            metadata={"run_id": run_id, "operation": "revision"},
        )
        return response
    except LookupError as exc:
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="run_failed",
            status="failed",
            error=str(exc),
            metadata={"run_id": run_id, "operation": "revision"},
        )
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        await workflow_event_bus.publish_document(
            document_id=str(document_id),
            reason="run_failed",
            status="failed",
            error=str(exc),
            metadata={"run_id": run_id, "operation": "revision"},
        )
        raise HTTPException(status_code=400, detail=str(exc)) from exc
