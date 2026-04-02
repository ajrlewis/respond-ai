"""LangGraph node implementations for the RFP workflow."""

from __future__ import annotations

import uuid
from contextlib import asynccontextmanager
from datetime import UTC, datetime
import logging
import re
from typing import AsyncIterator, Literal

from langgraph.types import interrupt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import get_chat_model, get_embedding_model, get_structured_model
from app.ai.providers import AIConfigurationError, AIProviderError
from app.ai.schemas import (
    DraftMetadataResult,
    EvidenceSynthesisResult,
    QuestionClassificationResult,
    RevisionIntentResult,
)
from app.core.config import settings
from app.db.models import RFPReview, RFPSession
from app.graph.state import WorkflowState
from app.graph.tools import keyword_search, semantic_search
from app.prompts import render_prompt_template as render_central_prompt_template
from app.prompts.drafting import (
    draft_metadata_system_prompt,
    draft_metadata_user_prompt,
    revision_intent_system_prompt,
    revision_intent_user_prompt,
)
from app.prompts.system import get_tone_guidelines
from app.services.observability import (
    create_node_run,
    finalize_node_run,
    get_observability_context,
    push_node_context,
    reset_observability_context,
    summarize_workflow_state,
)
from app.services.retrieval import RetrievalService
from app.services.embeddings import EmbeddingService

logger = logging.getLogger(__name__)


def render_prompt_template(prompt_name: str, template_name: str, **context: str) -> str:
    """Backwards-compatible wrapper around centralized prompt registry."""

    return render_central_prompt_template(prompt_name, template_name, **context)


def format_evidence_blob(evidence: list[dict]) -> str:
    """Format retrieved evidence chunks into a deterministic, citeable block."""

    return "\n\n".join(
        (
            f"[{idx + 1}] chunk_id={item.get('chunk_id', '')} "
            f"{item.get('document_filename', 'unknown')}#chunk-{item.get('chunk_index', 'n/a')}\n"
            f"{item.get('text', '')}"
        )
        for idx, item in enumerate(evidence)
    )


def build_structured_confidence_payload(
    *,
    metadata: DraftMetadataResult | None = None,
    synthesis: EvidenceSynthesisResult | None = None,
    retrieval_notes: str = "",
    fallback_score: float | None = None,
    fallback_compliance: Literal["passed", "needs_review", "unknown"] = "unknown",
    fallback_notes: str = "",
    fallback_gaps: list[str] | None = None,
) -> dict:
    """Build structured confidence metadata for API and UI rendering."""

    if metadata:
        missing_info = list(metadata.missing_info_notes)
        if synthesis:
            missing_info = sorted(
                {
                    item.strip()
                    for item in [*missing_info, *synthesis.missing_information]
                    if isinstance(item, str) and item.strip()
                }
            )
        score = 0.78
        if missing_info:
            score -= 0.18
        if metadata.compliance_flags:
            score -= 0.18
        score = max(0.0, min(1.0, score))
        return {
            "score": round(score, 2),
            "compliance_status": "needs_review" if metadata.compliance_flags else "passed",
            "model_notes": metadata.confidence_notes.strip(),
            "retrieval_notes": retrieval_notes.strip(),
            "evidence_gaps": missing_info,
        }

    return {
        "score": fallback_score,
        "compliance_status": fallback_compliance,
        "model_notes": fallback_notes.strip(),
        "retrieval_notes": retrieval_notes.strip(),
        "evidence_gaps": list(fallback_gaps or []),
    }


def render_confidence_notes(confidence_payload: dict) -> str:
    """Render a readable confidence summary from structured payload."""

    notes = [
        (
            f"Confidence score (heuristic): {confidence_payload['score']:.2f}."
            if isinstance(confidence_payload.get("score"), (float, int))
            else "Confidence score (heuristic): Not available."
        ),
        (
            "Compliance status: Passed."
            if confidence_payload.get("compliance_status") == "passed"
            else (
                "Compliance status: Needs review."
                if confidence_payload.get("compliance_status") == "needs_review"
                else "Compliance status: Unknown."
            )
        ),
    ]

    model_notes = str(confidence_payload.get("model_notes", "")).strip()
    if model_notes:
        notes.append(f"Model notes: {model_notes}")

    evidence_gaps = [gap for gap in confidence_payload.get("evidence_gaps", []) if isinstance(gap, str) and gap.strip()]
    if evidence_gaps:
        notes.append(f"Evidence gaps: {'; '.join(evidence_gaps)}")

    retrieval_notes = str(confidence_payload.get("retrieval_notes", "")).strip()
    if retrieval_notes:
        notes.append(f"Retrieval notes: {retrieval_notes}")

    return " ".join(notes)


def evidence_item_key(item: dict) -> str:
    """Build a deterministic key for evidence filtering and UI selection."""

    chunk_id = str(item.get("chunk_id", "")).strip()
    if chunk_id:
        return chunk_id
    return f"{item.get('document_filename', 'unknown')}::{item.get('chunk_index', 'n/a')}"


def mark_excluded_evidence(evidence: list[dict], excluded_keys: list[str]) -> list[dict]:
    """Annotate evidence with reviewer exclusion flags."""

    excluded_lookup = {key.strip() for key in excluded_keys if key.strip()}
    marked = []
    for item in evidence:
        row = {**item}
        row["excluded_by_reviewer"] = evidence_item_key(row) in excluded_lookup
        marked.append(row)
    return marked


def active_evidence(evidence: list[dict]) -> list[dict]:
    """Return evidence remaining after reviewer exclusions."""

    return [item for item in evidence if not bool(item.get("excluded_by_reviewer", False))]


def append_answer_version(
    existing_versions: list[dict],
    answer_text: str,
    stage: Literal["draft", "revision", "final"],
    *,
    question_type: str | None = None,
    confidence_notes: str = "",
    confidence_payload: dict | None = None,
    revision_feedback: str = "",
    included_chunk_ids: list[str] | None = None,
    excluded_chunk_ids: list[str] | None = None,
) -> list[dict]:
    """Append immutable answer snapshots while skipping duplicate adjacent text."""

    normalized_answer = answer_text.strip()
    if not normalized_answer:
        return existing_versions

    if existing_versions and existing_versions[-1].get("answer_text", "").strip() == normalized_answer:
        return existing_versions

    existing_numbers = [
        int(item.get("version_number", 0))
        for item in existing_versions
        if isinstance(item, dict) and str(item.get("version_number", "")).isdigit()
    ]
    next_index = (max(existing_numbers) if existing_numbers else len(existing_versions)) + 1
    label = f"Draft {next_index}" if stage != "final" else "Final"
    score = confidence_payload.get("score") if isinstance(confidence_payload, dict) else None
    snapshot = {
        "version_id": str(uuid.uuid4()),
        "version_number": next_index,
        "label": label,
        "stage": stage,
        "answer_text": normalized_answer,
        "content": normalized_answer,
        "status": "approved" if stage == "final" else "draft",
        "revision_feedback": revision_feedback.strip() or None,
        "included_chunk_ids": list(included_chunk_ids or []),
        "excluded_chunk_ids": list(excluded_chunk_ids or []),
        "question_type": question_type,
        "confidence_notes": confidence_notes.strip() or None,
        "confidence_score": float(score) if isinstance(score, (int, float)) else None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return [*existing_versions, snapshot]


def _latest_version_index(versions: list[dict]) -> int | None:
    """Return the index of the latest version row by version_number."""

    best_index: int | None = None
    best_number = -1
    for index, item in enumerate(versions):
        if not isinstance(item, dict):
            continue
        raw = item.get("version_number")
        if isinstance(raw, int):
            number = raw
        elif isinstance(raw, str) and raw.isdigit():
            number = int(raw)
        else:
            number = index + 1
        if number >= best_number:
            best_number = number
            best_index = index
    return best_index


def _audit_evidence_rows(evidence: list[dict]) -> list[dict]:
    """Normalize evidence rows for immutable audit snapshots."""

    rows: list[dict] = []
    for item in evidence:
        rows.append(
            {
                "chunk_id": str(item.get("chunk_id", "")).strip() or None,
                "document_id": str(item.get("document_id", "")).strip() or None,
                "document_title": str(item.get("document_title", "")).strip(),
                "document_filename": str(item.get("document_filename", "")).strip(),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
                "retrieval_method": str(item.get("retrieval_method", "")).strip(),
                "text": str(item.get("text", "")).strip(),
                "excluded_by_reviewer": bool(item.get("excluded_by_reviewer", False)),
                "metadata": item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
            }
        )
    return rows


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

    async def ask(self, state: WorkflowState) -> WorkflowState:
        """Create a business session and initialize workflow state."""

        node_run_id, context_token = await self._start_node_observation("ask", state)
        thread_id = state.get("thread_id") or str(uuid.uuid4())
        question_text = state["question_text"].strip()
        tone = state.get("tone", "formal")
        logger.info(
            "Node ask started thread_id=%s tone=%s question_chars=%d",
            thread_id,
            tone,
            len(question_text),
        )

        try:
            async with self._db() as db:
                existing = (
                    await db.execute(select(RFPSession).where(RFPSession.graph_thread_id == thread_id))
                ).scalar_one_or_none()
                if existing:
                    existing.current_node = "ask"
                    await db.commit()
                    logger.info("Node ask reused existing session session_id=%s thread_id=%s", existing.id, thread_id)
                    output = {
                        "thread_id": thread_id,
                        "session_id": str(existing.id),
                        "status": existing.status,
                        "tone": existing.tone,
                        "current_node": "ask",
                    }
                    await self._finish_node_observation(
                        node_run_id=node_run_id,
                        context_token=context_token,
                        output_state=output,
                        status="success",
                    )
                    return output

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
                logger.info("Node ask created session session_id=%s thread_id=%s", session.id, thread_id)
                output = {
                    "thread_id": thread_id,
                    "session_id": str(session.id),
                    "status": session.status,
                    "tone": session.tone,
                    "current_node": "ask",
                }
                await self._finish_node_observation(
                    node_run_id=node_run_id,
                    context_token=context_token,
                    output_state=output,
                    status="success",
                )
                return output
        except BaseException as exc:
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if self._is_human_wait_interrupt(exc) else "error",
                error_message=None if self._is_human_wait_interrupt(exc) else str(exc),
            )
            raise

    async def classify_question(self, state: WorkflowState) -> WorkflowState:
        """Classify question type using small model with heuristic fallback."""

        node_run_id, context_token = await self._start_node_observation("classify_question", state)
        try:
            await self._set_current_node(state.get("session_id"), "classify_question")
            question_text = state["question_text"]
            logger.debug(
                "Node classify_question started session_id=%s question_chars=%d",
                state.get("session_id"),
                len(question_text),
            )
            classification = await self._classify_with_model(question_text)
            category = classification.question_type
            logger.info("Node classify_question completed session_id=%s category=%s", state.get("session_id"), category)

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.question_type = category
                    await db.commit()

            output = {
                "question_type": category,
                "classification": classification.model_dump(),
                "current_node": "classify_question",
                "session_id": state.get("session_id"),
            }
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    async def retrieve_evidence(self, state: WorkflowState) -> WorkflowState:
        """Retrieve evidence through semantic and keyword methods."""

        node_run_id, context_token = await self._start_node_observation("retrieve_evidence", state)
        try:
            await self._set_current_node(state.get("session_id"), "retrieve_evidence")
            query = state["question_text"]
            logger.debug("Node retrieve_evidence started session_id=%s", state.get("session_id"))

            async with self._db() as db:
                embedding_service = self._optional_embedding_service()
                retrieval = RetrievalService(db=db, embedding_service=embedding_service)

                semantic = await semantic_search(retrieval, query, settings.retrieval_top_k)
                keyword = await keyword_search(retrieval, query, settings.retrieval_top_k)
                merged = semantic + keyword
            logger.info(
                "Node retrieve_evidence completed session_id=%s semantic=%d keyword=%d merged=%d",
                state.get("session_id"),
                len(semantic),
                len(keyword),
                len(merged),
            )
            output = {"retrieved_evidence": merged, "current_node": "retrieve_evidence", "session_id": state.get("session_id")}
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    async def cross_reference_evidence(self, state: WorkflowState) -> WorkflowState:
        """Dedupe/rerank retrieved chunks and identify evidence quality gaps."""

        node_run_id, context_token = await self._start_node_observation("cross_reference_evidence", state)
        try:
            await self._set_current_node(state.get("session_id"), "cross_reference_evidence")
            candidates = state.get("retrieved_evidence", [])
            logger.debug(
                "Node cross_reference_evidence started session_id=%s candidate_count=%d",
                state.get("session_id"),
                len(candidates),
            )
            if not candidates:
                logger.warning("No evidence candidates found session_id=%s", state.get("session_id"))
                confidence_payload = build_structured_confidence_payload(
                    fallback_score=0.0,
                    fallback_compliance="unknown",
                    fallback_notes="No relevant internal evidence was retrieved.",
                    fallback_gaps=["No relevant internal evidence was retrieved."],
                )
                output = {
                    "curated_evidence": [],
                    "evidence_synthesis": {},
                    "confidence_notes": render_confidence_notes(confidence_payload),
                    "confidence_payload": confidence_payload,
                    "current_node": "cross_reference_evidence",
                    "session_id": state.get("session_id"),
                }
                await self._finish_node_observation(
                    node_run_id=node_run_id,
                    context_token=context_token,
                    output_state=output,
                    status="success",
                )
                return output

            ranked = curate_evidence(candidates, final_k=settings.final_evidence_k)
            synthesis = await self._cross_reference_with_model(
                question=state.get("question_text", ""),
                question_type=state.get("question_type", "other"),
                evidence=ranked,
            )
            if synthesis and synthesis.selected_chunk_ids:
                selected_ids = {item.strip() for item in synthesis.selected_chunk_ids if item.strip()}
                filtered_ranked = [
                    item
                    for item in ranked
                    if str(item.get("chunk_id", "")).strip() in selected_ids
                    or evidence_item_key(item) in selected_ids
                ]
                if filtered_ranked:
                    ranked = filtered_ranked

            confidence_notes = build_confidence_notes(ranked)
            retrieval_notes = confidence_notes
            if synthesis and synthesis.evidence_summary.strip():
                retrieval_notes = f"{confidence_notes} {synthesis.evidence_summary.strip()}".strip()

            confidence_payload = build_structured_confidence_payload(
                synthesis=synthesis,
                fallback_score=None,
                fallback_compliance="unknown",
                fallback_notes="; ".join(synthesis.contradictions_found) if synthesis else "",
                fallback_gaps=synthesis.missing_information if synthesis else [],
                retrieval_notes=retrieval_notes,
            )
            logger.info(
                "Node cross_reference_evidence completed session_id=%s curated_count=%d",
                state.get("session_id"),
                len(ranked),
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.evidence_payload = ranked
                    session.confidence_notes = retrieval_notes
                    session.confidence_payload = confidence_payload
                    await db.commit()

            output = {
                "curated_evidence": ranked,
                "evidence_synthesis": synthesis.model_dump() if synthesis else {},
                "confidence_notes": retrieval_notes,
                "confidence_payload": confidence_payload,
                "current_node": "cross_reference_evidence",
                "session_id": state.get("session_id"),
            }
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    async def draft_response(self, state: WorkflowState) -> WorkflowState:
        """Draft investor-grade response grounded in evidence."""

        node_run_id, context_token = await self._start_node_observation("draft_response", state)
        try:
            await self._set_current_node(state.get("session_id"), "draft_response")
            logger.debug(
                "Node draft_response started session_id=%s evidence_count=%d",
                state.get("session_id"),
                len(state.get("curated_evidence", [])),
            )
            answer, confidence_notes, confidence_payload, draft_metadata = await self._draft_answer(
                question=state["question_text"],
                question_type=state.get("question_type", "other"),
                tone=state.get("tone", "formal"),
                evidence=state.get("curated_evidence", []),
                existing_confidence=state.get("confidence_notes", ""),
                synthesis=state.get("evidence_synthesis", {}),
            )
            logger.info(
                "Node draft_response completed session_id=%s answer_chars=%d",
                state.get("session_id"),
                len(answer),
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.draft_answer = answer
                    session.confidence_notes = confidence_notes
                    session.confidence_payload = {**confidence_payload, "draft_metadata": draft_metadata}
                    session.evidence_gaps_acknowledged = False
                    session.evidence_gaps_acknowledged_at = None
                    session.status = "awaiting_review"
                    await db.commit()

            output = {
                "draft_answer": answer,
                "draft_origin": "initial",
                "draft_metadata": draft_metadata,
                "confidence_notes": confidence_notes,
                "confidence_payload": {**confidence_payload, "draft_metadata": draft_metadata},
                "status": "awaiting_review",
                "current_node": "draft_response",
                "session_id": state.get("session_id"),
            }
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    async def polish_response(self, state: WorkflowState) -> WorkflowState:
        """Apply a final tone-polish pass before human review."""

        node_run_id, context_token = await self._start_node_observation("polish_response", state)
        try:
            await self._set_current_node(state.get("session_id"), "polish_response")
            logger.debug("Node polish_response started session_id=%s", state.get("session_id"))

            draft_text = state.get("draft_answer", "")
            evidence_for_snapshot = state.get("curated_evidence", [])
            included_chunk_ids = [
                evidence_item_key(item)
                for item in active_evidence(evidence_for_snapshot)
            ]
            excluded_chunk_ids = [
                evidence_item_key(item)
                for item in evidence_for_snapshot
                if bool(item.get("excluded_by_reviewer", False))
            ]
            polished_text = await self._polish_answer(
                question=state.get("question_text", ""),
                question_type=state.get("question_type", "other"),
                tone=state.get("tone", "formal"),
                draft_answer=draft_text,
                evidence=active_evidence(evidence_for_snapshot),
            )
            stage: Literal["draft", "revision"] = "revision" if state.get("draft_origin") == "revision" else "draft"
            logger.info(
                "Node polish_response completed session_id=%s original_chars=%d polished_chars=%d stage=%s",
                state.get("session_id"),
                len(draft_text),
                len(polished_text),
                stage,
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    next_versions = append_answer_version(
                        list(getattr(session, "answer_versions_payload", []) or []),
                        polished_text,
                        stage,
                        question_type=state.get("question_type"),
                        confidence_notes=state.get("confidence_notes", ""),
                        confidence_payload=state.get("confidence_payload", {}),
                        revision_feedback=state.get("review_comments", "") if stage == "revision" else "",
                        included_chunk_ids=included_chunk_ids,
                        excluded_chunk_ids=excluded_chunk_ids,
                    )
                    session.draft_answer = polished_text
                    session.answer_versions_payload = next_versions
                    await db.commit()

            output = {
                "draft_answer": polished_text,
                "answer_versions": append_answer_version(
                    state.get("answer_versions", []),
                    polished_text,
                    stage,
                    question_type=state.get("question_type"),
                    confidence_notes=state.get("confidence_notes", ""),
                    confidence_payload=state.get("confidence_payload", {}),
                    revision_feedback=state.get("review_comments", "") if stage == "revision" else "",
                    included_chunk_ids=included_chunk_ids,
                    excluded_chunk_ids=excluded_chunk_ids,
                ),
                "current_node": "polish_response",
                "session_id": state.get("session_id"),
            }
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    async def human_review(self, state: WorkflowState) -> WorkflowState:
        """Pause graph for human review and resume with action payload."""

        node_run_id, context_token = await self._start_node_observation("human_review", state)
        try:
            await self._set_current_node(state.get("session_id"), "human_review")
            logger.info("Node human_review interrupting session_id=%s", state.get("session_id"))
            review_payload = interrupt(
                {
                    "session_id": state["session_id"],
                    "question_text": state["question_text"],
                    "draft_answer": state.get("draft_answer", ""),
                    "confidence_notes": state.get("confidence_notes", ""),
                    "confidence_payload": state.get("confidence_payload", {}),
                    "evidence": state.get("curated_evidence", []),
                    "answer_versions": state.get("answer_versions", []),
                }
            )

            review_action = review_payload.get("reviewer_action", "revise")
            reviewer_id = str(review_payload.get("reviewer_id", "")).strip()
            review_comments = review_payload.get("review_comments", "")
            edited_answer = review_payload.get("edited_answer", "")
            excluded_evidence_keys = [
                key.strip() for key in review_payload.get("excluded_evidence_keys", []) if isinstance(key, str) and key.strip()
            ]
            reviewed_evidence_gaps = bool(review_payload.get("reviewed_evidence_gaps", False))
            logger.info(
                "Node human_review resumed session_id=%s action=%s comments_chars=%d edited_chars=%d excluded=%d",
                state.get("session_id"),
                review_action,
                len(review_comments),
                len(edited_answer),
                len(excluded_evidence_keys),
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.status = "revision_requested" if review_action == "revise" else "awaiting_finalization"
                    await db.commit()

            output = {
                "review_action": review_action,
                "reviewer_id": reviewer_id,
                "review_comments": review_comments,
                "edited_answer": edited_answer,
                "excluded_evidence_keys": excluded_evidence_keys,
                "reviewed_evidence_gaps": reviewed_evidence_gaps,
                "current_node": "human_review",
                "session_id": state.get("session_id"),
            }
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    async def revise_response(self, state: WorkflowState) -> WorkflowState:
        """Revise draft based on reviewer feedback."""

        node_run_id, context_token = await self._start_node_observation("revise_response", state)
        try:
            await self._set_current_node(state.get("session_id"), "revise_response")
            logger.debug(
                "Node revise_response started session_id=%s feedback_chars=%d",
                state.get("session_id"),
                len(state.get("review_comments", "")),
            )
            prior_evidence = state.get("curated_evidence", [])
            requested_exclusions = [
                key.strip()
                for key in state.get("excluded_evidence_keys", [])
                if isinstance(key, str) and key.strip()
            ]
            merged_exclusions = sorted(set(requested_exclusions))
            marked_evidence = mark_excluded_evidence(prior_evidence, merged_exclusions)
            filtered_evidence = active_evidence(marked_evidence)
            retrieval_notes = str((state.get("confidence_payload") or {}).get("retrieval_notes", "")).strip()
            if requested_exclusions:
                retrieval_notes = (
                    f"{retrieval_notes} Reviewer excluded {len(requested_exclusions)} chunk(s) for this revision."
                ).strip()

            revised_answer, confidence_notes, confidence_payload, revision_intent, draft_metadata = await self._revise_answer(
                question=state["question_text"],
                question_type=state.get("question_type", "other"),
                prior_draft=state.get("draft_answer", ""),
                evidence=filtered_evidence,
                reviewer_feedback=state.get("review_comments", ""),
                tone=state.get("tone", "formal"),
                retrieval_notes=retrieval_notes,
            )
            logger.info(
                "Node revise_response completed session_id=%s answer_chars=%d evidence_used=%d evidence_excluded=%d",
                state.get("session_id"),
                len(revised_answer),
                len(filtered_evidence),
                len(merged_exclusions),
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.draft_answer = revised_answer
                    session.confidence_notes = confidence_notes
                    session.confidence_payload = {
                        **confidence_payload,
                        "revision_intent": revision_intent,
                        "draft_metadata": draft_metadata,
                    }
                    session.evidence_payload = marked_evidence
                    session.evidence_gaps_acknowledged = False
                    session.evidence_gaps_acknowledged_at = None
                    session.status = "awaiting_review"
                    await db.commit()

            output = {
                "draft_answer": revised_answer,
                "draft_origin": "revision",
                "curated_evidence": marked_evidence,
                "revision_intent": revision_intent,
                "draft_metadata": draft_metadata,
                "confidence_notes": confidence_notes,
                "confidence_payload": {
                    **confidence_payload,
                    "revision_intent": revision_intent,
                    "draft_metadata": draft_metadata,
                },
                "status": "awaiting_review",
                "excluded_evidence_keys": merged_exclusions,
                "review_action": "",
                "current_node": "revise_response",
                "session_id": state.get("session_id"),
            }
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    async def finalize_response(self, state: WorkflowState) -> WorkflowState:
        """Persist final approved answer."""

        node_run_id, context_token = await self._start_node_observation("finalize_response", state)
        try:
            await self._set_current_node(state.get("session_id"), "finalize_response")
            logger.info(
                "Node finalize_response started session_id=%s has_edited_answer=%s",
                state.get("session_id"),
                bool(state.get("edited_answer")),
            )

            final_answer = ""
            final_version_number: int | None = None
            approved_at = datetime.now(UTC)

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    final_answer = (getattr(session, "draft_answer", None) or state.get("draft_answer", "")).strip()
                    if not final_answer:
                        final_answer = str(state.get("edited_answer", "")).strip()

                    evidence_for_snapshot = state.get("curated_evidence", []) or list(getattr(session, "evidence_payload", []) or [])
                    included_chunk_ids = [
                        evidence_item_key(item)
                        for item in active_evidence(evidence_for_snapshot)
                    ]
                    excluded_chunk_ids = [
                        evidence_item_key(item)
                        for item in evidence_for_snapshot
                        if bool(item.get("excluded_by_reviewer", False))
                    ]

                    existing_versions = list(getattr(session, "answer_versions_payload", []) or [])
                    latest_index = _latest_version_index(existing_versions)
                    if latest_index is None:
                        next_versions = append_answer_version(
                            existing_versions,
                            final_answer,
                            "final",
                            question_type=state.get("question_type"),
                            confidence_notes=state.get("confidence_notes", ""),
                            confidence_payload=state.get("confidence_payload", {}),
                            revision_feedback=state.get("review_comments", ""),
                            included_chunk_ids=included_chunk_ids,
                            excluded_chunk_ids=excluded_chunk_ids,
                        )
                        latest_index = _latest_version_index(next_versions)
                    else:
                        next_versions = []
                        for index, item in enumerate(existing_versions):
                            if not isinstance(item, dict):
                                next_versions.append(item)
                                continue
                            row = {**item}
                            is_latest = index == latest_index
                            row["status"] = "approved" if is_latest else "historical"
                            if is_latest:
                                row["stage"] = "final"
                                row["answer_text"] = final_answer
                                row["content"] = final_answer
                                row["included_chunk_ids"] = included_chunk_ids
                                row["excluded_chunk_ids"] = excluded_chunk_ids
                                if state.get("review_comments"):
                                    row["revision_feedback"] = state.get("review_comments", "")
                                score = (state.get("confidence_payload") or {}).get("score")
                                row["confidence_score"] = float(score) if isinstance(score, (int, float)) else None
                                row["confidence_notes"] = state.get("confidence_notes", "") or None
                            next_versions.append(row)

                    if latest_index is None:
                        final_version_number = None
                    else:
                        latest_row = next_versions[latest_index] if latest_index < len(next_versions) else {}
                        if isinstance(latest_row, dict) and str(latest_row.get("version_number", "")).isdigit():
                            final_version_number = int(str(latest_row.get("version_number")))
                        elif isinstance(latest_row, dict) and isinstance(latest_row.get("version_number"), int):
                            final_version_number = int(latest_row.get("version_number"))
                        else:
                            final_version_number = latest_index + 1

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
                    review_history = [
                        {
                            "id": str(item.id),
                            "reviewer_action": item.reviewer_action,
                            "reviewer_id": item.reviewer_id,
                            "review_comments": item.review_comments,
                            "edited_answer": item.edited_answer,
                            "excluded_evidence_keys": list(item.excluded_evidence_keys or []),
                            "reviewed_evidence_gaps": bool(item.reviewed_evidence_gaps),
                            "evidence_gaps_acknowledged_at": (
                                item.evidence_gaps_acknowledged_at.isoformat()
                                if getattr(item, "evidence_gaps_acknowledged_at", None)
                                else None
                            ),
                            "created_at": item.created_at.isoformat(),
                        }
                        for item in review_rows
                    ]

                    reviewer_id = str(state.get("reviewer_id", "")).strip() or None
                    if not reviewer_id:
                        for event in reversed(review_history):
                            if event.get("reviewer_action") == "approve" and event.get("reviewer_id"):
                                reviewer_id = str(event.get("reviewer_id"))
                                break

                    session.final_answer = final_answer
                    session.final_version_number = final_version_number
                    session.approved_at = approved_at
                    session.reviewer_action = "approve"
                    session.reviewer_id = reviewer_id
                    session.answer_versions_payload = next_versions
                    session.final_audit_payload = {
                        "version_number": final_version_number,
                        "timestamp": approved_at.isoformat(),
                        "reviewer_action": "approve",
                        "reviewer_id": reviewer_id,
                        "final_answer": final_answer,
                        "included_chunk_ids": included_chunk_ids,
                        "excluded_chunk_ids": excluded_chunk_ids,
                        "selected_evidence": _audit_evidence_rows(active_evidence(evidence_for_snapshot)),
                        "confidence_score": (state.get("confidence_payload") or {}).get("score"),
                        "confidence_notes": state.get("confidence_notes", ""),
                        "confidence_payload": state.get("confidence_payload", {}) or {},
                        "evidence_gap_count": len((state.get("confidence_payload") or {}).get("evidence_gaps", []) or []),
                        "evidence_gaps_acknowledged": bool(getattr(session, "evidence_gaps_acknowledged", False)),
                        "evidence_gaps_acknowledged_at": (
                            session.evidence_gaps_acknowledged_at.isoformat()
                            if getattr(session, "evidence_gaps_acknowledged_at", None)
                            else None
                        ),
                        "review_history": review_history,
                    }
                    session.status = "approved"
                    await db.commit()
                    logger.info("Node finalize_response persisted session_id=%s", state.get("session_id"))

            output = {
                "final_answer": final_answer,
                "final_version_number": final_version_number,
                "approved_at": approved_at.isoformat(),
                "status": "approved",
                "current_node": "finalize_response",
                "session_id": state.get("session_id"),
            }
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=output,
                status="success",
            )
            return output
        except BaseException as exc:
            is_interrupt = self._is_human_wait_interrupt(exc)
            await self._finish_node_observation(
                node_run_id=node_run_id,
                context_token=context_token,
                output_state=state,
                status="waiting_for_human" if is_interrupt else "error",
                error_message=None if is_interrupt else str(exc),
            )
            raise

    def _optional_embedding_service(self) -> EmbeddingService | None:
        try:
            model = get_embedding_model()
            logger.debug("Embedding service available provider=%s model=%s", model.provider, model.model)
            return EmbeddingService(model=model)
        except (AIConfigurationError, AIProviderError) as exc:
            logger.warning("Embedding service unavailable; semantic retrieval will be skipped error=%s", exc)
            return None

    async def _classify_with_model(self, question_text: str) -> QuestionClassificationResult:
        try:
            classifier = get_structured_model(
                schema=QuestionClassificationResult,
                purpose="classification",
            )
            classification = await classifier.ainvoke(
                system_prompt=render_prompt_template("classify_question", "system"),
                user_prompt=render_prompt_template("classify_question", "user", question_text=question_text),
                temperature=0,
            )
            logger.debug("Question classification completed via model category=%s", classification.question_type)
            return classification
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.info("Question classification model unavailable; using heuristic fallback error=%s", exc)

        lowered = question_text.lower()
        if "esg" in lowered or "sustainability" in lowered:
            category = "esg"
        elif "risk" in lowered or "regulator" in lowered or "policy" in lowered:
            category = "risk"
        elif "team" in lowered:
            category = "team"
        elif "different" in lowered or "edge" in lowered:
            category = "differentiation"
        elif "track record" in lowered or "example" in lowered:
            category = "track_record"
        elif "process" in lowered or "due diligence" in lowered:
            category = "operations"
        elif "strategy" in lowered or "renewable" in lowered:
            category = "strategy"
        else:
            category = "other"
        return QuestionClassificationResult(
            question_type=category,
            reasoning_summary="Heuristic fallback applied because structured classifier was unavailable.",
            suggested_retrieval_strategy="hybrid",
            confidence=0.45,
        )

    async def _cross_reference_with_model(
        self,
        *,
        question: str,
        question_type: str,
        evidence: list[dict],
    ) -> EvidenceSynthesisResult | None:
        if not evidence:
            return None

        try:
            synthesizer = get_structured_model(
                schema=EvidenceSynthesisResult,
                purpose="cross_reference",
            )
            return await synthesizer.ainvoke(
                system_prompt=render_prompt_template("analyze_evidence", "system"),
                user_prompt=render_prompt_template(
                    "analyze_evidence",
                    "user",
                    question=question,
                    question_type=question_type,
                    evidence=format_evidence_blob(evidence),
                ),
                temperature=0,
            )
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("Evidence synthesis fallback applied error=%s", exc)
            return None

    @staticmethod
    def _extract_citations(answer_text: str) -> list[str]:
        citations = re.findall(r"\[[^\]]+#chunk-\d+\]", answer_text)
        ordered: list[str] = []
        seen: set[str] = set()
        for citation in citations:
            token = citation.strip()
            if token and token not in seen:
                ordered.append(token)
                seen.add(token)
        return ordered

    async def _extract_draft_metadata(
        self,
        *,
        question: str,
        question_type: str,
        draft_answer: str,
        evidence_blob: str,
        purpose: Literal["draft_metadata", "revision_intent"] = "draft_metadata",
    ) -> DraftMetadataResult:
        try:
            extractor = get_structured_model(schema=DraftMetadataResult, purpose=purpose)
            return await extractor.ainvoke(
                system_prompt=draft_metadata_system_prompt(),
                user_prompt=draft_metadata_user_prompt(
                    question=question,
                    question_type=question_type,
                    draft_answer=draft_answer,
                    evidence=evidence_blob,
                ),
                temperature=0,
            )
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("Draft metadata extraction fallback applied error=%s", exc)

        compliance_flags: list[str] = []
        lowered = draft_answer.lower()
        for phrase in ["guaranteed", "guarantee", "certain returns", "no risk"]:
            if phrase in lowered:
                compliance_flags.append(f"Potential promissory language detected: '{phrase}'.")

        missing_notes = []
        if "insufficient" in lowered or "unable" in lowered:
            missing_notes.append("Answer indicates potentially missing evidence coverage.")

        return DraftMetadataResult(
            citations_used=self._extract_citations(draft_answer),
            coverage_notes="Fallback metadata extraction was used.",
            confidence_notes="Structured metadata extraction was unavailable; reviewer should verify citations and tone.",
            missing_info_notes=missing_notes,
            compliance_flags=compliance_flags,
        )

    async def _extract_revision_intent(
        self,
        *,
        question: str,
        reviewer_feedback: str,
    ) -> RevisionIntentResult:
        feedback = reviewer_feedback.strip() or "No additional reviewer comments provided."
        try:
            extractor = get_structured_model(schema=RevisionIntentResult, purpose="revision_intent")
            return await extractor.ainvoke(
                system_prompt=revision_intent_system_prompt(),
                user_prompt=revision_intent_user_prompt(question=question, reviewer_feedback=feedback),
                temperature=0,
            )
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("Revision intent extraction fallback applied error=%s", exc)

        return RevisionIntentResult(
            reviewer_request_summary=feedback,
            changes_requested=[feedback],
            expected_improvements=["Improve alignment with reviewer feedback while preserving citations."],
        )

    async def _draft_answer(
        self,
        *,
        question: str,
        question_type: str,
        tone: str,
        evidence: list[dict],
        existing_confidence: str,
        synthesis: dict | None = None,
    ) -> tuple[str, str, dict, dict]:
        if not evidence:
            logger.warning("Draft requested without evidence; returning low-confidence response")
            confidence_payload = build_structured_confidence_payload(
                fallback_score=0.0,
                fallback_compliance="unknown",
                fallback_notes="No supporting chunks were retrieved.",
                fallback_gaps=["No supporting chunks were retrieved."],
                retrieval_notes=existing_confidence,
            )
            return (
                "Insufficient internal evidence was retrieved to confidently draft a response. "
                "Please add internal material before finalizing this answer.",
                render_confidence_notes(confidence_payload),
                confidence_payload,
                {},
            )

        evidence_blob = format_evidence_blob(evidence)
        tone_guidelines = get_tone_guidelines(tone)
        synthesis_obj = EvidenceSynthesisResult.model_validate(synthesis or {}) if synthesis else None

        try:
            drafter = get_chat_model(purpose="drafting")
            draft_text = await drafter.ainvoke(
                system_prompt=render_prompt_template("draft_answer", "system"),
                user_prompt=render_prompt_template(
                    "draft_answer",
                    "user",
                    tone=tone,
                    tone_guidelines=tone_guidelines,
                    question_type=question_type,
                    question=question,
                    evidence=evidence_blob,
                ),
            )
            draft_text = draft_text.strip()
            metadata = await self._extract_draft_metadata(
                question=question,
                question_type=question_type,
                draft_answer=draft_text,
                evidence_blob=evidence_blob,
            )
            confidence_payload = build_structured_confidence_payload(
                metadata=metadata,
                synthesis=synthesis_obj,
                retrieval_notes=existing_confidence,
            )
            return draft_text, render_confidence_notes(confidence_payload), confidence_payload, metadata.model_dump()
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("Draft answer model unavailable; using deterministic fallback error=%s", exc)
            citations = ", ".join(
                f"[{item.get('document_filename', 'unknown')}#chunk-{item.get('chunk_index', 'n/a')}]"
                for item in evidence[:4]
            )
            fallback = (
                "Our renewable and sustainable investing approach focuses on contracted cash-flow assets, "
                "disciplined risk controls, and active asset management across solar and storage platforms. "
                "The strategy integrates ESG screening, due diligence, and ongoing monitoring across the "
                "investment lifecycle, with regulatory and policy risk tracked continuously. "
                f"Key evidence: {citations}."
            )
            metadata = DraftMetadataResult(
                citations_used=self._extract_citations(fallback),
                coverage_notes="Fallback deterministic draft was used.",
                confidence_notes="Draft generated without live model inference.",
                missing_info_notes=[],
                compliance_flags=[],
            )
            confidence_payload = build_structured_confidence_payload(
                metadata=metadata,
                synthesis=synthesis_obj,
                fallback_score=0.45,
                fallback_compliance="unknown",
                fallback_notes="Draft generated using deterministic fallback due to unavailable model.",
                retrieval_notes=existing_confidence,
            )
            return fallback, render_confidence_notes(confidence_payload), confidence_payload, metadata.model_dump()

    async def _revise_answer(
        self,
        *,
        question: str,
        question_type: str,
        prior_draft: str,
        evidence: list[dict],
        reviewer_feedback: str,
        tone: str,
        retrieval_notes: str,
    ) -> tuple[str, str, dict, dict, dict]:
        if not evidence:
            confidence_payload = build_structured_confidence_payload(
                fallback_score=0.1,
                fallback_compliance="needs_review",
                fallback_notes="All evidence was excluded by reviewer; additional source material is required.",
                fallback_gaps=["All available citation chunks were excluded by the reviewer."],
                retrieval_notes=retrieval_notes,
            )
            return (
                "Revision could not be completed because all citation chunks were excluded. "
                "Please provide replacement evidence or relax exclusions.",
                render_confidence_notes(confidence_payload),
                confidence_payload,
                {},
                {},
            )

        evidence_blob = format_evidence_blob(evidence)
        tone_guidelines = get_tone_guidelines(tone)
        revision_intent = await self._extract_revision_intent(
            question=question,
            reviewer_feedback=reviewer_feedback,
        )

        try:
            reviser = get_chat_model(purpose="revision")
            revised_text = await reviser.ainvoke(
                system_prompt=render_prompt_template("revise_answer", "system"),
                user_prompt=render_prompt_template(
                    "revise_answer",
                    "user",
                    tone=tone,
                    tone_guidelines=tone_guidelines,
                    question=question,
                    reviewer_feedback=reviewer_feedback or "No additional reviewer comments provided.",
                    reviewer_intent=revision_intent.reviewer_request_summary,
                    prior_draft=prior_draft or "No prior draft available.",
                    evidence=evidence_blob,
                ),
            )
            revised_text = revised_text.strip()
            metadata = await self._extract_draft_metadata(
                question=question,
                question_type=question_type,
                draft_answer=revised_text,
                evidence_blob=evidence_blob,
                purpose="draft_metadata",
            )
            confidence_payload = build_structured_confidence_payload(
                metadata=metadata,
                retrieval_notes=retrieval_notes,
            )
            return (
                revised_text,
                render_confidence_notes(confidence_payload),
                confidence_payload,
                revision_intent.model_dump(),
                metadata.model_dump(),
            )
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("Revision model unavailable; using deterministic fallback error=%s", exc)
            revised_text = (
                f"{prior_draft}\n\nReviewer-requested revision integrated: "
                f"{reviewer_feedback.strip() or 'No additional comments provided.'}"
            )
            metadata = DraftMetadataResult(
                citations_used=self._extract_citations(revised_text),
                coverage_notes="Fallback deterministic revision was used.",
                confidence_notes="Revision generated without live model inference.",
                missing_info_notes=[],
                compliance_flags=[],
            )
            confidence_payload = build_structured_confidence_payload(
                metadata=metadata,
                fallback_score=None,
                fallback_compliance="unknown",
                fallback_notes="Revision produced via fallback because model inference is unavailable.",
                retrieval_notes=retrieval_notes,
            )
            return (
                revised_text,
                render_confidence_notes(confidence_payload),
                confidence_payload,
                revision_intent.model_dump(),
                metadata.model_dump(),
            )

    async def _polish_answer(
        self,
        *,
        question: str,
        question_type: str,
        tone: str,
        draft_answer: str,
        evidence: list[dict],
    ) -> str:
        """Polish tone with constrained edits while preserving citations."""

        stripped = draft_answer.strip()
        if not stripped:
            return draft_answer

        evidence_blob = format_evidence_blob(evidence)
        tone_guidelines = get_tone_guidelines(tone)
        try:
            polisher = get_chat_model(purpose="polish")
            output = await polisher.ainvoke(
                system_prompt=render_prompt_template("polish_answer", "system"),
                user_prompt=render_prompt_template(
                    "polish_answer",
                    "user",
                    tone=tone,
                    tone_guidelines=tone_guidelines,
                    question_type=question_type,
                    question=question,
                    draft_answer=stripped,
                    evidence=evidence_blob,
                ),
                temperature=0,
            )
            polished = output.strip()
            return polished or stripped
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("Tone polish model unavailable; returning unmodified draft error=%s", exc)
            return stripped


def curate_evidence(candidates: list[dict], final_k: int) -> list[dict]:
    """Deduplicate and rerank evidence by score and method diversity."""

    logger.debug("Curating evidence candidates=%d final_k=%d", len(candidates), final_k)
    deduped: dict[str, dict] = {}
    for item in candidates:
        chunk_id = item["chunk_id"]
        current = deduped.get(chunk_id)
        if current is None:
            deduped[chunk_id] = {**item, "methods": {item.get("retrieval_method", "unknown")}}
            continue

        current["score"] = max(float(current.get("score", 0.0)), float(item.get("score", 0.0)))
        current["methods"].add(item.get("retrieval_method", "unknown"))

    reranked = []
    for item in deduped.values():
        method_bonus = 0.15 if len(item["methods"]) > 1 else 0.0
        item["score"] = float(item.get("score", 0.0)) + method_bonus
        item["retrieval_method"] = "+".join(sorted(item["methods"]))
        item.pop("methods", None)
        reranked.append(item)

    reranked.sort(key=lambda evidence: evidence.get("score", 0.0), reverse=True)
    results = reranked[:final_k]
    logger.debug("Evidence curation completed deduped=%d selected=%d", len(deduped), len(results))
    return results


def build_confidence_notes(curated_evidence: list[dict]) -> str:
    """Build confidence notes based on evidence quality heuristics."""

    if not curated_evidence:
        logger.debug("Confidence notes requested with no evidence")
        return "No evidence available."

    docs = {item["document_filename"] for item in curated_evidence}
    methods = {item.get("retrieval_method", "") for item in curated_evidence}
    avg_score = sum(float(item.get("score", 0.0)) for item in curated_evidence) / len(curated_evidence)

    notes = [
        f"Retrieved {len(curated_evidence)} supporting chunks from {len(docs)} source documents.",
        f"Average relevance score: {avg_score:.2f}.",
    ]

    if len(docs) < 2:
        notes.append("Coverage is concentrated in a small number of documents; consider additional validation.")
    if not any("semantic" in method for method in methods):
        notes.append("Semantic retrieval unavailable; response relies on keyword matching.")
    if avg_score < 0.2:
        notes.append("Overall evidence quality appears weak; treat response as low confidence.")

    result = " ".join(notes)
    logger.debug(
        "Confidence notes built evidence_count=%d doc_count=%d method_count=%d avg_score=%.2f",
        len(curated_evidence),
        len(docs),
        len(methods),
        avg_score,
    )
    return result
