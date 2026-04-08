"""Routes for document-centric drafting and versioning."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
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

router = APIRouter(
    prefix="/api/response-documents",
    tags=["response-documents"],
)
logger = logging.getLogger(__name__)


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
    try:
        return await service.generate_document(
            document_id,
            tone=payload.tone,
            created_by=payload.created_by,
        )
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
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
    try:
        return await service.ai_revise(document_id, payload)
    except LookupError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
