"""Service layer for response-document drafting, versioning, and AI revision."""

from __future__ import annotations

import asyncio
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable
import uuid
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.core.database import AsyncSessionLocal
from app.db.models import (
    RFPSession,
    ResponseDocument,
    ResponseDocumentSection,
    ResponseDocumentVersion,
    ResponseQuestion,
)
from app.graph.runtime import resume_from_review, run_until_human_review
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
from app.services.evidence_analysis import active_evidence, optional_embedding_service
from app.services.response_document_utils import (
    EXAMPLE_QUESTIONS,
    build_diff_segments,
    compose_document_text,
    coverage_to_score,
    extract_questions,
    normalize_title,
    section_text_map,
)
from app.services.retrieval import RetrievalService
from app.services.session_service import SessionService
from app.services.workflow_events import workflow_event_bus


@dataclass(slots=True)
class _HydratedDocument:
    document: ResponseDocument
    questions: list[ResponseQuestion]
    versions: list[ResponseDocumentVersion]


DocumentProgressCallback = Callable[[str, str, str, dict[str, Any] | None], Awaitable[None]]
AgentOperation = str

GENERATION_NODE_STAGE_LABELS: dict[str, str] = {
    "classify_and_plan": "Plan approach",
    "adaptive_retrieve": "Retrieve supporting material",
    "evaluate_evidence": "Rank evidence",
    "draft_response": "Draft response sections",
    "polish_response": "Review citations",
}

REVISION_NODE_STAGE_LABELS: dict[str, str] = {
    "human_review": "Analyze revision request",
    "revise_response": "Revise draft text",
    "polish_response": "Prepare editable suggestions",
}


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
        progress: DocumentProgressCallback | None = None,
    ) -> ResponseDocumentOut:
        """Generate answers for all questions via LangGraph and save as a new version."""

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

        session_service = SessionService(self.db)
        total_questions = len(questions)
        for question_index, question in enumerate(questions, start=1):
            thread_id = str(uuid.uuid4())
            session = await session_service.create_or_get_session(
                thread_id=thread_id,
                question_text=question.extracted_text,
                tone=tone,
            )
            question.metadata_json = {
                **(question.metadata_json or {}),
                "agent_thread_id": thread_id,
                "agent_session_id": str(session.id),
            }

            await self._run_with_session_progress(
                session_id=str(session.id),
                operation="generation",
                progress=progress,
                question_index=question_index,
                question_total=total_questions,
                runner=lambda: run_until_human_review(
                    {
                        "thread_id": thread_id,
                        "question_text": question.extracted_text,
                        "tone": tone,
                        "session_id": str(session.id),
                    },
                    thread_id=thread_id,
                ),
            )

            refreshed_session = await self._load_agent_session_snapshot(thread_id)
            if not refreshed_session:
                raise LookupError("Generated agent session was not found.")
            section_payload = self._build_section_from_session(
                question=question,
                session=refreshed_session,
                draft_version_id=version.id,
            )
            self.db.add(
                ResponseDocumentSection(
                    draft_version_id=version.id,
                    question_id=question.id,
                    order_index=question.order_index,
                    content_markdown=section_payload.content_markdown,
                    evidence_refs_payload=section_payload.evidence_refs_payload,
                    confidence_score=section_payload.confidence_score,
                    coverage_score=section_payload.coverage_score,
                    metadata_json=section_payload.metadata_json,
                )
            )
            await self.db.flush()
            if progress is not None:
                await progress(
                    f"question_complete:q{question_index}",
                    "Review citations",
                    "done",
                    {
                        "question_index": question_index,
                        "question_total": total_questions,
                        "question_completed": True,
                        "question_id": str(question.id),
                        "content_markdown": section_payload.content_markdown,
                        "evidence_refs": section_payload.evidence_refs_payload,
                    },
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
                    metadata_json=dict(parent_section.metadata_json or {}) if parent_section else {},
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
        *,
        progress: DocumentProgressCallback | None = None,
    ) -> AIReviseResponse:
        """Return AI-revised section drafts via LangGraph review-resume."""

        hydrated = await self._load_document(document_id)
        base = self._pick_version(hydrated.versions, payload.base_version_id)
        if not base:
            raise ValueError("A saved base version is required before AI revision.")

        question_by_id = {question.id: question for question in hydrated.questions}
        base_sections = {section.question_id: section for section in base.sections}
        target_question_ids = [payload.question_id] if payload.question_id else [item.id for item in hydrated.questions]

        session_service = SessionService(self.db)
        revised_sections: list[SaveSectionInput] = []
        total_targets = len(target_question_ids)
        for target_index, question_id in enumerate(target_question_ids, start=1):
            question = question_by_id.get(question_id)
            section = base_sections.get(question_id)
            if not question or not section:
                continue

            session = await self._ensure_agent_session_for_section(
                question=question,
                section=section,
                tone=payload.tone,
                session_service=session_service,
            )
            feedback = payload.instruction.strip()
            if payload.selected_text and payload.selected_text.strip():
                feedback = (
                    f"{feedback}\n\nFocus on this selected text:\n"
                    f"{payload.selected_text.strip()}"
                )

            await self._run_with_session_progress(
                session_id=str(session.id),
                operation="revision",
                progress=progress,
                question_index=target_index,
                question_total=total_targets,
                runner=lambda: resume_from_review(
                    thread_id=session.graph_thread_id,
                    review_payload={
                        "session_id": str(session.id),
                        "reviewer_action": "revise",
                        "review_comments": feedback,
                        "edited_answer": section.content_markdown,
                        "reviewer_id": "",
                        "excluded_evidence_keys": [],
                        "reviewed_evidence_gaps": True,
                        "evidence_gaps_acknowledged": True,
                    },
                ),
            )

            refreshed = await self._load_agent_session_snapshot(session.graph_thread_id)
            if not refreshed:
                raise LookupError("Revised agent session was not found.")
            evidence_refs = self._session_evidence_refs(refreshed)
            confidence_payload = refreshed.confidence_payload or {}
            revised_sections.append(
                SaveSectionInput(
                    question_id=question_id,
                    content_markdown=(refreshed.draft_answer or section.content_markdown or "").strip(),
                    evidence_refs=evidence_refs,
                    confidence_score=confidence_payload.get("score"),
                    coverage_score=coverage_to_score(confidence_payload.get("coverage")),
                )
            )

        return AIReviseResponse(base_version_id=base.id, revised_sections=revised_sections)

    async def _run_with_session_progress(
        self,
        *,
        session_id: str,
        operation: AgentOperation,
        progress: DocumentProgressCallback | None,
        question_index: int | None = None,
        question_total: int | None = None,
        runner: Callable[[], Awaitable[dict]],
    ) -> dict:
        if progress is None:
            return await runner()

        ready = asyncio.Event()
        stop = asyncio.Event()
        startup_error: list[Exception] = []

        async def consume() -> None:
            try:
                async with workflow_event_bus.subscribe_session(session_id) as subscription:
                    ready.set()
                    while not stop.is_set():
                        signal = await subscription.next_event(timeout=0.4)
                        if signal is None or signal.reason != "node_started":
                            continue
                        label = self._stage_label_for_node(signal.node_name, operation=operation)
                        if not label:
                            continue
                        stage_id = signal.node_name or label
                        stage_meta: dict[str, Any] | None = None
                        if question_index is not None and question_total is not None:
                            stage_id = f"{stage_id}:q{question_index}"
                            stage_meta = {
                                "question_index": question_index,
                                "question_total": question_total,
                            }
                        await progress(stage_id, label, "running", stage_meta)
            except Exception as exc:  # pragma: no cover - defensive guard against stalled progress stream
                startup_error.append(exc)
                ready.set()

        consumer = asyncio.create_task(consume())
        await ready.wait()
        if startup_error:
            with suppress(asyncio.CancelledError):
                consumer.cancel()
                await consumer
            return await runner()
        try:
            return await runner()
        finally:
            stop.set()
            with suppress(asyncio.TimeoutError):
                await asyncio.wait_for(consumer, timeout=1.5)
            if not consumer.done():
                consumer.cancel()
                with suppress(asyncio.CancelledError):
                    await consumer

    async def _ensure_agent_session_for_section(
        self,
        *,
        question: ResponseQuestion,
        section: ResponseDocumentSection,
        tone: str,
        session_service: SessionService,
    ) -> RFPSession:
        metadata = section.metadata_json if isinstance(section.metadata_json, dict) else {}
        thread_id = self._metadata_value(metadata, "agent_thread_id") or self._metadata_value(
            question.metadata_json if isinstance(question.metadata_json, dict) else {},
            "agent_thread_id",
        )
        session = await self._load_agent_session_snapshot(thread_id) if thread_id else None

        if session is None:
            thread_id = str(uuid.uuid4())
            session = await session_service.create_or_get_session(
                thread_id=thread_id,
                question_text=question.extracted_text,
                tone=tone,
            )
            question.metadata_json = {
                **(question.metadata_json or {}),
                "agent_thread_id": thread_id,
                "agent_session_id": str(session.id),
            }
            await self.db.commit()
            await run_until_human_review(
                {
                    "thread_id": thread_id,
                    "question_text": question.extracted_text,
                    "tone": tone,
                    "session_id": str(session.id),
                },
                thread_id=thread_id,
            )
            refreshed = await self._load_agent_session_snapshot(thread_id)
            session = refreshed or session

        return session

    async def _load_agent_session_snapshot(self, thread_id: str | None) -> RFPSession | None:
        """Load an RFPSession in a fresh DB session to avoid stale in-request identity-map state."""

        if not thread_id:
            return None
        async with AsyncSessionLocal() as read_db:
            service = SessionService(read_db)
            return await service.get_session_by_thread_id(thread_id)

    @staticmethod
    def _metadata_value(metadata: dict[str, object] | None, key: str) -> str | None:
        if not isinstance(metadata, dict):
            return None
        value = metadata.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
        return None

    @staticmethod
    def _stage_label_for_node(node_name: str | None, *, operation: AgentOperation) -> str | None:
        if not node_name:
            return None
        if operation == "revision":
            label = REVISION_NODE_STAGE_LABELS.get(node_name)
            if label:
                return label
        return GENERATION_NODE_STAGE_LABELS.get(node_name)

    def _session_evidence_refs(self, session: RFPSession) -> list[EvidenceChunk]:
        selected = [item for item in (session.selected_evidence_payload or []) if isinstance(item, dict)]
        base_rows = selected or active_evidence(list(session.evidence_payload or []))
        evidence_refs: list[EvidenceChunk] = []
        for row in base_rows:
            try:
                evidence_refs.append(EvidenceChunk.model_validate(row))
            except Exception:
                continue
        return evidence_refs

    def _build_section_from_session(
        self,
        *,
        question: ResponseQuestion,
        session: RFPSession,
        draft_version_id: UUID,
    ) -> ResponseDocumentSection:
        evidence_refs = self._session_evidence_refs(session)
        confidence_payload = session.confidence_payload or {}
        content = (session.draft_answer or "").strip()

        return ResponseDocumentSection(
            draft_version_id=draft_version_id,
            question_id=question.id,
            order_index=question.order_index,
            content_markdown=content,
            evidence_refs_payload=[item.model_dump(mode="json") for item in evidence_refs],
            confidence_score=confidence_payload.get("score"),
            coverage_score=coverage_to_score(confidence_payload.get("coverage")),
            metadata_json={
                "agent_thread_id": session.graph_thread_id,
                "agent_session_id": str(session.id),
            },
        )

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
