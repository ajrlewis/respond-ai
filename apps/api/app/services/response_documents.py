"""Service layer for response-document drafting, versioning, and AI revision."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.db.models import (
    ResponseDocument,
    ResponseDocumentSection,
    ResponseDocumentVersion,
    ResponseQuestion,
)
from app.schemas.documents import EvidenceChunk
from app.schemas.response_documents import (
    AIReviseRequest,
    AIReviseResponse,
    CompareResponseVersionsOut,
    CreateResponseDocumentRequest,
    ResponseDocumentOut,
    ResponseQuestionOut,
    ResponseSectionOut,
    ResponseVersionOut,
    ResponseVersionSummaryOut,
    SaveResponseVersionRequest,
    SaveSectionInput,
)
from app.services.drafting import draft_answer, revise_answer
from app.services.evidence_analysis import optional_embedding_service
from app.services.response_document_utils import (
    EXAMPLE_QUESTIONS,
    build_diff_segments,
    compose_document_text,
    coverage_to_score,
    extract_questions,
    normalize_title,
    section_text_map,
)
from app.services.retrieval import RetrievalService, chunk_to_dict


@dataclass(slots=True)
class _HydratedDocument:
    document: ResponseDocument
    questions: list[ResponseQuestion]
    versions: list[ResponseDocumentVersion]


class ResponseDocumentService:
    """Create, generate, revise, and version response documents."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        # Use the same embedding availability gate as graph retrieval:
        # semantic search is enabled when embedding config is valid.
        self.retrieval = RetrievalService(db, embedding_service=optional_embedding_service())

    async def create_document(self, payload: CreateResponseDocumentRequest) -> ResponseDocumentOut:
        """Create a response document from source text, explicit questions, or defaults."""

        questions = [item.strip() for item in payload.questions if item.strip()]
        if payload.use_example_questions and not questions:
            questions = list(EXAMPLE_QUESTIONS)
        if not questions and payload.source_text:
            questions = extract_questions(payload.source_text)
        if not questions:
            questions = list(EXAMPLE_QUESTIONS)

        title = (payload.title or "").strip() or "Response Draft"
        document = ResponseDocument(
            title=title,
            source_filename=payload.source_filename,
            source_text=payload.source_text,
            status="ready_to_generate",
            created_by=payload.created_by,
            metadata_json={},
        )
        self.db.add(document)
        await self.db.flush()

        for index, question_text in enumerate(questions):
            self.db.add(
                ResponseQuestion(
                    response_document_id=document.id,
                    order_index=index,
                    extracted_text=question_text,
                    normalized_title=normalize_title(question_text),
                    metadata_json={},
                )
            )

        await self.db.commit()
        return await self.get_document(document.id)

    async def get_document(
        self,
        document_id: UUID,
        *,
        selected_version_id: UUID | None = None,
    ) -> ResponseDocumentOut:
        """Return editor view payload for a response document."""

        hydrated = await self._load_document(document_id)
        selected_version = self._pick_version(hydrated.versions, selected_version_id)

        return ResponseDocumentOut(
            id=hydrated.document.id,
            title=hydrated.document.title,
            source_filename=hydrated.document.source_filename,
            status=hydrated.document.status,
            created_at=hydrated.document.created_at,
            updated_at=hydrated.document.updated_at,
            questions=[
                ResponseQuestionOut(
                    id=question.id,
                    order_index=question.order_index,
                    extracted_text=question.extracted_text,
                    normalized_title=question.normalized_title,
                )
                for question in hydrated.questions
            ],
            versions=[self._version_summary(version) for version in hydrated.versions],
            selected_version=self._version_detail(selected_version) if selected_version else None,
        )

    async def list_versions(self, document_id: UUID) -> list[ResponseVersionSummaryOut]:
        """Return all saved versions for a document."""

        hydrated = await self._load_document(document_id)
        return [self._version_summary(version) for version in hydrated.versions]

    async def approve_version(
        self,
        document_id: UUID,
        *,
        version_id: UUID,
    ) -> ResponseDocumentOut:
        """Mark one version as approved/final for the document."""

        hydrated = await self._load_document(document_id)
        selected = self._pick_version(hydrated.versions, version_id)
        if not selected:
            raise LookupError("Version not found for this response document.")

        for version in hydrated.versions:
            version.is_final = version.id == selected.id
        hydrated.document.status = "approved"
        await self.db.commit()
        return await self.get_document(document_id, selected_version_id=selected.id)

    async def delete_version(
        self,
        document_id: UUID,
        *,
        version_id: UUID,
    ) -> ResponseDocumentOut:
        """Delete one saved version and return the refreshed document state."""

        hydrated = await self._load_document(document_id)
        selected = self._pick_version(hydrated.versions, version_id)
        if not selected:
            raise LookupError("Version not found for this response document.")

        was_final = selected.is_final
        await self.db.delete(selected)
        await self.db.flush()

        remaining = [version for version in hydrated.versions if version.id != version_id]
        next_selected_id: UUID | None = None
        if remaining:
            if was_final:
                for version in remaining:
                    version.is_final = False
                remaining[-1].is_final = True
            next_selected_id = remaining[-1].id
            hydrated.document.status = "approved" if any(version.is_final for version in remaining) else "draft_ready"
        else:
            hydrated.document.status = "ready_to_generate"

        await self.db.commit()
        return await self.get_document(document_id, selected_version_id=next_selected_id)

    async def generate_document(
        self,
        document_id: UUID,
        *,
        tone: str,
        created_by: str | None,
    ) -> ResponseDocumentOut:
        """Generate answers for all questions and save as a new version."""

        hydrated = await self._load_document(document_id)
        questions = hydrated.questions
        if not questions:
            raise ValueError("Document has no questions.")

        parent = hydrated.versions[-1] if hydrated.versions else None
        next_version_number = (parent.version_number + 1) if parent else 1
        version = ResponseDocumentVersion(
            response_document_id=document_id,
            version_number=next_version_number,
            label=f"Version {next_version_number}",
            created_by=created_by,
            parent_version_id=parent.id if parent else None,
            is_final=False,
            metadata_json={"generated": True},
        )
        self.db.add(version)
        await self.db.flush()

        for question in questions:
            retrieved = await self.retrieval.hybrid_search(question.extracted_text, top_k=6)
            evidence = [chunk_to_dict(item) for item in retrieved]
            draft_text, _, confidence_payload, _ = await draft_answer(
                question=question.extracted_text,
                question_type="general",
                tone=tone,
                evidence=evidence,
                existing_confidence="",
                synthesis={},
                retrieval_plan={},
                evidence_evaluation={},
                retrieval_strategy_used=None,
            )
            self.db.add(
                ResponseDocumentSection(
                    draft_version_id=version.id,
                    question_id=question.id,
                    order_index=question.order_index,
                    content_markdown=draft_text,
                    evidence_refs_payload=evidence,
                    confidence_score=confidence_payload.get("score"),
                    coverage_score=coverage_to_score(confidence_payload.get("coverage")),
                    metadata_json={},
                )
            )

        hydrated.document.status = "draft_ready"
        await self.db.commit()
        return await self.get_document(document_id, selected_version_id=version.id)

    async def save_new_version(
        self,
        document_id: UUID,
        payload: SaveResponseVersionRequest,
    ) -> ResponseDocumentOut:
        """Save current editor state as a new durable version."""

        hydrated = await self._load_document(document_id)
        parent = self._pick_version(hydrated.versions, payload.based_on_version_id)
        if parent is None and hydrated.versions:
            parent = hydrated.versions[-1]

        next_version_number = (parent.version_number + 1) if parent else 1
        label = (payload.label or "").strip() or f"Version {next_version_number}"
        now = datetime.now(UTC)

        version = ResponseDocumentVersion(
            response_document_id=document_id,
            version_number=next_version_number,
            label=label,
            created_by=payload.created_by,
            parent_version_id=parent.id if parent else None,
            is_final=False,
            metadata_json={"saved_at": now.isoformat()},
        )
        self.db.add(version)
        await self.db.flush()

        parent_sections: dict[UUID, ResponseDocumentSection] = {}
        if parent:
            parent_sections = {section.question_id: section for section in parent.sections}
        submitted = {item.question_id: item for item in payload.sections}

        for question in hydrated.questions:
            section_input = submitted.get(question.id)
            parent_section = parent_sections.get(question.id)
            evidence_refs = section_input.evidence_refs if section_input else []
            if not evidence_refs and parent_section:
                evidence_refs = [
                    EvidenceChunk.model_validate(item) for item in (parent_section.evidence_refs_payload or [])
                ]
            content = section_input.content_markdown if section_input else (parent_section.content_markdown if parent_section else "")
            confidence = (
                section_input.confidence_score
                if section_input and section_input.confidence_score is not None
                else (parent_section.confidence_score if parent_section else None)
            )
            coverage = (
                section_input.coverage_score
                if section_input and section_input.coverage_score is not None
                else (parent_section.coverage_score if parent_section else None)
            )
            self.db.add(
                ResponseDocumentSection(
                    draft_version_id=version.id,
                    question_id=question.id,
                    order_index=question.order_index,
                    content_markdown=content,
                    evidence_refs_payload=[item.model_dump(mode="json") for item in evidence_refs],
                    confidence_score=confidence,
                    coverage_score=coverage,
                    metadata_json={},
                )
            )

        hydrated.document.status = "draft_ready"
        await self.db.commit()
        return await self.get_document(document_id, selected_version_id=version.id)

    async def compare_versions(
        self,
        document_id: UUID,
        *,
        left_version_id: UUID,
        right_version_id: UUID,
    ) -> CompareResponseVersionsOut:
        """Compute a readable diff between two saved versions."""

        hydrated = await self._load_document(document_id)
        left = self._pick_version(hydrated.versions, left_version_id)
        right = self._pick_version(hydrated.versions, right_version_id)
        if not left or not right:
            raise ValueError("One or both version ids were not found.")

        left_map = section_text_map(left)
        right_map = section_text_map(right)
        document_segments = build_diff_segments(
            compose_document_text(hydrated.questions, left_map),
            compose_document_text(hydrated.questions, right_map),
        )

        section_diffs: list[dict] = []
        for question in hydrated.questions:
            left_text = left_map.get(question.id, "")
            right_text = right_map.get(question.id, "")
            section_diffs.append(
                {
                    "question_id": str(question.id),
                    "question_text": question.extracted_text,
                    "segments": build_diff_segments(left_text, right_text),
                }
            )

        return CompareResponseVersionsOut(
            left=self._version_summary(left),
            right=self._version_summary(right),
            segments=document_segments,
            section_diffs=section_diffs,
        )

    async def ai_revise(
        self,
        document_id: UUID,
        payload: AIReviseRequest,
    ) -> AIReviseResponse:
        """Return AI-revised section drafts without auto-saving a version."""

        hydrated = await self._load_document(document_id)
        base = self._pick_version(hydrated.versions, payload.base_version_id)
        if not base:
            raise ValueError("A saved base version is required before AI revision.")

        question_by_id = {question.id: question for question in hydrated.questions}
        base_sections = {section.question_id: section for section in base.sections}
        target_question_ids = [payload.question_id] if payload.question_id else [item.id for item in hydrated.questions]

        revised_sections: list[SaveSectionInput] = []
        for question_id in target_question_ids:
            question = question_by_id.get(question_id)
            section = base_sections.get(question_id)
            if not question or not section:
                continue

            evidence_refs = [
                EvidenceChunk.model_validate(item)
                for item in (section.evidence_refs_payload or [])
            ]
            feedback = payload.instruction.strip()
            if payload.selected_text and payload.selected_text.strip():
                feedback = (
                    f"{feedback}\n\nFocus on this selected text:\n"
                    f"{payload.selected_text.strip()}"
                )

            revised_text, _, confidence_payload, _, _ = await revise_answer(
                question=question.extracted_text,
                question_type="general",
                prior_draft=section.content_markdown,
                evidence=[item.model_dump(mode="json") for item in evidence_refs],
                reviewer_feedback=feedback,
                tone=payload.tone,
                retrieval_notes="",
            )

            revised_sections.append(
                SaveSectionInput(
                    question_id=question_id,
                    content_markdown=revised_text,
                    evidence_refs=evidence_refs,
                    confidence_score=confidence_payload.get("score"),
                    coverage_score=coverage_to_score(confidence_payload.get("coverage")),
                )
            )

        return AIReviseResponse(base_version_id=base.id, revised_sections=revised_sections)

    async def _load_document(self, document_id: UUID) -> _HydratedDocument:
        stmt = (
            select(ResponseDocument)
            .where(ResponseDocument.id == document_id)
            .execution_options(populate_existing=True)
            .options(
                selectinload(ResponseDocument.questions),
                selectinload(ResponseDocument.versions).selectinload(ResponseDocumentVersion.sections),
            )
        )
        document = (await self.db.execute(stmt)).scalar_one_or_none()
        if not document:
            raise LookupError("Response document not found.")
        questions = sorted(list(document.questions or []), key=lambda item: item.order_index)
        versions = sorted(list(document.versions or []), key=lambda item: item.version_number)
        return _HydratedDocument(document=document, questions=questions, versions=versions)

    @staticmethod
    def _pick_version(
        versions: list[ResponseDocumentVersion],
        selected_version_id: UUID | None,
    ) -> ResponseDocumentVersion | None:
        if not versions:
            return None
        if selected_version_id:
            for version in versions:
                if version.id == selected_version_id:
                    return version
            return None
        return versions[-1]

    @staticmethod
    def _version_summary(version: ResponseDocumentVersion) -> ResponseVersionSummaryOut:
        return ResponseVersionSummaryOut(
            id=version.id,
            version_number=version.version_number,
            label=version.label,
            created_by=version.created_by,
            parent_version_id=version.parent_version_id,
            is_final=version.is_final,
            created_at=version.created_at,
        )

    @staticmethod
    def _version_detail(version: ResponseDocumentVersion) -> ResponseVersionOut:
        sections = sorted(list(version.sections or []), key=lambda item: item.order_index)
        return ResponseVersionOut(
            id=version.id,
            version_number=version.version_number,
            label=version.label,
            created_by=version.created_by,
            parent_version_id=version.parent_version_id,
            is_final=version.is_final,
            created_at=version.created_at,
            sections=[
                ResponseSectionOut(
                    id=section.id,
                    question_id=section.question_id,
                    order_index=section.order_index,
                    content_markdown=section.content_markdown,
                    confidence_score=section.confidence_score,
                    coverage_score=section.coverage_score,
                    evidence_refs=[
                        EvidenceChunk.model_validate(item)
                        for item in (section.evidence_refs_payload or [])
                    ],
                )
                for section in sections
            ],
        )
