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
    EvidenceEvaluationResult,
    EvidenceSynthesisResult,
    QuestionClassificationResult,
    RetrievalPlanResult,
    RevisionIntentResult,
)
from app.core.config import settings
from app.db.models import RFPReview, RFPSession
from app.graph.state import WorkflowState
from app.graph.tools import expand_chunk_context, keyword_search, semantic_search
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
    evaluation: EvidenceEvaluationResult | None = None,
    retrieval_strategy_used: str | None = None,
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
        if evaluation:
            missing_info = sorted(
                {
                    item.strip()
                    for item in [*missing_info, *evaluation.missing_information]
                    if isinstance(item, str) and item.strip()
                }
            )
        score = float(evaluation.confidence) if evaluation else 0.78
        if evaluation and evaluation.coverage == "partial":
            score -= 0.08
        if evaluation and evaluation.coverage == "weak":
            score -= 0.2
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
            "retrieval_strategy": (retrieval_strategy_used or "").strip() or None,
            "coverage": evaluation.coverage if evaluation else "unknown",
            "recommended_action": evaluation.recommended_action if evaluation else "unknown",
            "selected_chunk_ids": list(evaluation.selected_chunk_ids) if evaluation else [],
            "rejected_chunk_ids": list(evaluation.rejected_chunk_ids) if evaluation else [],
            "notes_for_drafting": list(evaluation.notes_for_drafting) if evaluation else [],
        }

    coverage = evaluation.coverage if evaluation else "unknown"
    recommended_action = evaluation.recommended_action if evaluation else "unknown"
    return {
        "score": (
            float(evaluation.confidence)
            if evaluation and isinstance(evaluation.confidence, (float, int))
            else fallback_score
        ),
        "compliance_status": fallback_compliance,
        "model_notes": fallback_notes.strip(),
        "retrieval_notes": retrieval_notes.strip(),
        "evidence_gaps": sorted(
            {
                item.strip()
                for item in [*(fallback_gaps or []), *(evaluation.missing_information if evaluation else [])]
                if isinstance(item, str) and item.strip()
            }
        ),
        "retrieval_strategy": (retrieval_strategy_used or "").strip() or None,
        "coverage": coverage,
        "recommended_action": recommended_action,
        "selected_chunk_ids": list(evaluation.selected_chunk_ids) if evaluation else [],
        "rejected_chunk_ids": list(evaluation.rejected_chunk_ids) if evaluation else [],
        "notes_for_drafting": list(evaluation.notes_for_drafting) if evaluation else [],
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

    retrieval_strategy = str(confidence_payload.get("retrieval_strategy", "")).strip()
    if retrieval_strategy:
        notes.append(f"Retrieval strategy: {retrieval_strategy}.")

    coverage = str(confidence_payload.get("coverage", "")).strip()
    if coverage:
        notes.append(f"Evidence coverage: {coverage}.")

    return " ".join(notes)


def retrieval_plan_fallback(question_text: str) -> RetrievalPlanResult:
    """Deterministic fallback plan when structured planner is unavailable."""

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
    elif "process" in lowered or "due diligence" in lowered or "operat" in lowered:
        category = "operations"
    elif "strategy" in lowered or "renewable" in lowered:
        category = "strategy"
    else:
        category = "other"

    needs_examples = any(token in lowered for token in ("example", "case", "track record", "value creation"))
    needs_quantitative_support = any(
        token in lowered for token in ("return", "performance", "kpi", "capacity", "mw", "%", "metric")
    )
    needs_regulatory_context = any(token in lowered for token in ("regulator", "sfdr", "policy", "compliance"))

    priority_sources = [category]
    if needs_examples:
        priority_sources.append("portfolio_examples")
    if needs_quantitative_support:
        priority_sources.append("performance_metrics")
    if needs_regulatory_context:
        priority_sources.append("regulatory_policy")

    return RetrievalPlanResult(
        question_type=category,
        reasoning_summary="Heuristic planning fallback applied because structured planner was unavailable.",
        sub_questions=[
            "What direct evidence answers the core question?",
            "What supporting examples demonstrate outcomes?",
            "What caveats or gaps remain based on available internal documents?",
        ],
        retrieval_strategy="hybrid",
        priority_sources=priority_sources,
        needs_examples=needs_examples,
        needs_quantitative_support=needs_quantitative_support,
        should_expand_context=needs_examples or needs_quantitative_support or needs_regulatory_context,
        needs_regulatory_context=needs_regulatory_context,
        needs_prior_answers=True,
        preferred_top_k=min(18, max(8, settings.retrieval_top_k)),
        confidence=0.45,
    )


def _chunk_search_blob(chunk: dict) -> str:
    parts = [
        str(chunk.get("document_title", "")),
        str(chunk.get("document_filename", "")),
        str(chunk.get("text", "")),
    ]
    metadata = chunk.get("metadata", {})
    if isinstance(metadata, dict):
        for key in ("source_type", "category", "tags", "title"):
            value = metadata.get(key)
            if isinstance(value, str):
                parts.append(value)
            elif isinstance(value, list):
                parts.extend(str(item) for item in value if isinstance(item, str))
    return " ".join(parts).lower()


def _chunk_has_numeric_signal(chunk: dict) -> bool:
    text = _chunk_search_blob(chunk)
    if re.search(r"\b\d+(\.\d+)?\s?(%|mw|gw|kwh|kpi|x)\b", text):
        return True
    return any(token in text for token in ("capacity", "metric", "performance", "irr", "moic", "yield"))


def _chunk_has_example_signal(chunk: dict) -> bool:
    text = _chunk_search_blob(chunk)
    return any(token in text for token in ("example", "case study", "portfolio", "investment", "asset", "value creation"))


def _chunk_matches_priority(chunk: dict, priorities: list[str]) -> bool:
    blob = _chunk_search_blob(chunk)
    return any(priority and priority in blob for priority in priorities)


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

    async def classify_and_plan(self, state: WorkflowState) -> WorkflowState:
        """Classify question and produce a structured retrieval plan."""

        node_run_id, context_token = await self._start_node_observation("classify_and_plan", state)
        try:
            await self._set_current_node(state.get("session_id"), "classify_and_plan")
            question_text = state["question_text"]
            logger.debug(
                "Node classify_and_plan started session_id=%s question_chars=%d",
                state.get("session_id"),
                len(question_text),
            )
            plan = await self._plan_retrieval_with_model(question_text)
            logger.info(
                "Node classify_and_plan completed session_id=%s category=%s strategy=%s sub_questions=%d",
                state.get("session_id"),
                plan.question_type,
                plan.retrieval_strategy,
                len(plan.sub_questions),
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.question_type = plan.question_type
                    session.retrieval_plan_payload = plan.model_dump()
                    session.retrieval_strategy_used = plan.retrieval_strategy
                    session.retry_count = int(state.get("retry_count", 0) or 0)
                    await db.commit()

            classification = QuestionClassificationResult(
                question_type=plan.question_type,
                reasoning_summary=plan.reasoning_summary,
                suggested_retrieval_strategy=plan.retrieval_strategy,
                confidence=plan.confidence,
            )
            output = {
                "question_type": plan.question_type,
                "classification": classification.model_dump(),
                "retrieval_plan": plan.model_dump(),
                "retry_count": int(state.get("retry_count", 0) or 0),
                "current_node": "classify_and_plan",
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

    async def classify_question(self, state: WorkflowState) -> WorkflowState:
        """Backward-compatible wrapper for legacy node name."""

        return await self.classify_and_plan(state)

    async def adaptive_retrieve(self, state: WorkflowState) -> WorkflowState:
        """Retrieve evidence adaptively based on the planner output."""

        node_run_id, context_token = await self._start_node_observation("adaptive_retrieve", state)
        try:
            await self._set_current_node(state.get("session_id"), "adaptive_retrieve")
            query = state["question_text"]
            retry_count = int(state.get("retry_count", 0) or 0)
            plan = RetrievalPlanResult.model_validate(state.get("retrieval_plan") or retrieval_plan_fallback(query).model_dump())
            config = self._build_retrieval_config(plan=plan, retry_count=retry_count)
            logger.debug(
                "Node adaptive_retrieve started session_id=%s strategy=%s retry=%d",
                state.get("session_id"),
                config["strategy"],
                retry_count,
            )

            semantic_results: list[dict] = []
            keyword_results: list[dict] = []
            context_results: list[dict] = []
            query_variants = [query, *[item for item in plan.sub_questions if isinstance(item, str) and item.strip()][:2]]
            keyword_queries = query_variants if config["strategy"] in {"keyword", "hybrid"} else []
            semantic_query = " ".join(query_variants) if config["strategy"] in {"semantic", "hybrid"} else ""

            async with self._db() as db:
                embedding_service = self._optional_embedding_service()
                retrieval = RetrievalService(db=db, embedding_service=embedding_service)

                if semantic_query:
                    semantic_results = await semantic_search(retrieval, semantic_query, int(config["semantic_top_k"]))

                if keyword_queries:
                    per_query_k = max(2, int(config["keyword_top_k"]) // max(1, len(keyword_queries)))
                    for variant in keyword_queries:
                        keyword_results.extend(await keyword_search(retrieval, variant, per_query_k))

                if not semantic_results and str(config["strategy"]) == "semantic":
                    keyword_results.extend(
                        await keyword_search(
                            retrieval,
                            query,
                            max(4, int(config["semantic_top_k"])),
                        )
                    )
                if not keyword_results and str(config["strategy"]) == "keyword":
                    semantic_results.extend(
                        await semantic_search(
                            retrieval,
                            query,
                            max(4, int(config["keyword_top_k"])),
                        )
                    )

                merged = self._apply_plan_scoring(
                    chunks=[*semantic_results, *keyword_results],
                    plan=plan,
                    retry_count=retry_count,
                )

                if bool(config["expand_context"]) and merged:
                    for chunk in merged[: int(config["expand_seed_count"])]:
                        chunk_id = str(chunk.get("chunk_id", "")).strip()
                        if chunk_id:
                            context_results.extend(
                                await expand_chunk_context(
                                    retrieval,
                                    chunk_id=chunk_id,
                                    window=int(config["context_window"]),
                                )
                            )
                    merged = self._apply_plan_scoring(
                        chunks=[*merged, *context_results],
                        plan=plan,
                        retry_count=retry_count,
                    )

            final_top_k = int(config["final_top_k"])
            retrieved = merged[:final_top_k]
            retrieval_debug = {
                "strategy": config["strategy"],
                "semantic_top_k": int(config["semantic_top_k"]),
                "keyword_top_k": int(config["keyword_top_k"]),
                "final_top_k": final_top_k,
                "expand_context": bool(config["expand_context"]),
                "context_window": int(config["context_window"]),
                "query_variants": query_variants,
                "priority_sources": list(plan.priority_sources),
                "semantic_results": len(semantic_results),
                "keyword_results": len(keyword_results),
                "context_results": len(context_results),
                "retrieved_chunk_ids": [str(item.get("chunk_id", "")) for item in retrieved],
                "retrieved_scores": [float(item.get("score", 0.0)) for item in retrieved],
                "retry_count": retry_count,
            }
            logger.info(
                "Node adaptive_retrieve completed session_id=%s strategy=%s retrieved=%d",
                state.get("session_id"),
                config["strategy"],
                len(retrieved),
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.retrieval_strategy_used = str(config["strategy"])
                    session.retrieval_metadata_payload = retrieval_debug
                    session.retrieval_plan_payload = plan.model_dump()
                    await db.commit()

            output = {
                "retrieval_plan": plan.model_dump(),
                "retrieval_strategy_used": str(config["strategy"]),
                "retrieval_debug": retrieval_debug,
                "retrieved_chunks": retrieved,
                "retrieved_evidence": retrieved,
                "current_node": "adaptive_retrieve",
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
        """Backward-compatible wrapper for legacy node name."""

        return await self.adaptive_retrieve(state)

    async def evaluate_evidence(self, state: WorkflowState) -> WorkflowState:
        """Evaluate evidence sufficiency and select draft-ready chunks."""

        node_run_id, context_token = await self._start_node_observation("evaluate_evidence", state)
        try:
            await self._set_current_node(state.get("session_id"), "evaluate_evidence")
            question = state.get("question_text", "")
            retry_count = int(state.get("retry_count", 0) or 0)
            plan = RetrievalPlanResult.model_validate(state.get("retrieval_plan") or retrieval_plan_fallback(question).model_dump())
            candidates = list(state.get("retrieved_evidence", []) or state.get("retrieved_chunks", []) or [])
            logger.debug(
                "Node evaluate_evidence started session_id=%s candidate_count=%d retry=%d",
                state.get("session_id"),
                len(candidates),
                retry_count,
            )

            evaluation = await self._evaluate_evidence_with_model(
                question=question,
                plan=plan,
                evidence=candidates,
            )
            evaluation = self._normalize_evaluation_result(evaluation=evaluation, evidence=candidates, plan=plan)
            selected, rejected, annotated = self._partition_evidence(
                evidence=candidates,
                selected_ids=evaluation.selected_chunk_ids,
                rejected_ids=evaluation.rejected_chunk_ids,
            )

            retrieval_strategy = str(state.get("retrieval_strategy_used", "")).strip() or plan.retrieval_strategy
            retrieval_notes = build_confidence_notes(selected or candidates)
            if evaluation.evidence_summary.strip():
                retrieval_notes = f"{retrieval_notes} {evaluation.evidence_summary.strip()}".strip()

            effective_retry_count = retry_count
            final_evaluation = evaluation
            if evaluation.recommended_action == "retrieve_more" and retry_count >= 1:
                final_evaluation = evaluation.model_copy(
                    update={
                        "recommended_action": "proceed_with_caveats",
                        "notes_for_drafting": [
                            *evaluation.notes_for_drafting,
                            "Additional retrieval was already attempted once; proceed with explicit caveats.",
                        ],
                    }
                )

            confidence_payload = build_structured_confidence_payload(
                evaluation=final_evaluation,
                retrieval_strategy_used=retrieval_strategy,
                retrieval_notes=retrieval_notes,
                fallback_score=0.35 if final_evaluation.coverage == "weak" else 0.55,
                fallback_compliance="unknown",
                fallback_notes="Evidence evaluation completed without draft metadata extraction.",
                fallback_gaps=final_evaluation.missing_information,
            )
            confidence_notes = render_confidence_notes(confidence_payload)

            next_plan = plan
            if final_evaluation.recommended_action == "retrieve_more" and retry_count < 1:
                effective_retry_count = retry_count + 1
                next_plan = self._augment_plan_for_retry(plan=plan, evaluation=final_evaluation)

            logger.info(
                "Node evaluate_evidence completed session_id=%s coverage=%s selected=%d rejected=%d action=%s retry=%d",
                state.get("session_id"),
                final_evaluation.coverage,
                len(selected),
                len(rejected),
                final_evaluation.recommended_action,
                effective_retry_count,
            )

            async with self._db() as db:
                session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
                if session:
                    session.evidence_payload = annotated
                    session.selected_evidence_payload = selected
                    session.rejected_evidence_payload = rejected
                    session.evidence_evaluation_payload = final_evaluation.model_dump()
                    session.retrieval_plan_payload = next_plan.model_dump()
                    session.retrieval_strategy_used = retrieval_strategy
                    session.retry_count = effective_retry_count
                    session.confidence_notes = confidence_notes
                    session.confidence_payload = confidence_payload
                    await db.commit()

            output = {
                "retrieval_plan": next_plan.model_dump(),
                "retrieval_strategy_used": retrieval_strategy,
                "retry_count": effective_retry_count,
                "selected_evidence": selected,
                "rejected_evidence": rejected,
                "curated_evidence": selected,
                "evidence_evaluation": final_evaluation.model_dump(),
                "confidence_notes": confidence_notes,
                "confidence_payload": confidence_payload,
                "current_node": "evaluate_evidence",
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
            selected_evidence = state.get("selected_evidence", []) or state.get("curated_evidence", [])
            logger.debug(
                "Node draft_response started session_id=%s evidence_count=%d",
                state.get("session_id"),
                len(selected_evidence),
            )
            answer, confidence_notes, confidence_payload, draft_metadata = await self._draft_answer(
                question=state["question_text"],
                question_type=state.get("question_type", "other"),
                tone=state.get("tone", "formal"),
                evidence=selected_evidence,
                existing_confidence=state.get("confidence_notes", ""),
                synthesis=state.get("evidence_synthesis", {}),
                retrieval_plan=state.get("retrieval_plan", {}),
                evidence_evaluation=state.get("evidence_evaluation", {}),
                retrieval_strategy_used=state.get("retrieval_strategy_used"),
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
                    session.selected_evidence_payload = selected_evidence
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
                        "retrieval_plan": state.get("retrieval_plan") or getattr(session, "retrieval_plan_payload", {}) or {},
                        "retrieval_strategy": (
                            state.get("retrieval_strategy_used")
                            or getattr(session, "retrieval_strategy_used", None)
                        ),
                        "evidence_evaluation": (
                            state.get("evidence_evaluation")
                            or getattr(session, "evidence_evaluation_payload", {}) or {}
                        ),
                        "retry_count": int(
                            state.get("retry_count")
                            if state.get("retry_count") is not None
                            else getattr(session, "retry_count", 0)
                        ),
                        "selected_chunk_ids": list(
                            {
                                str(item.get("chunk_id", "")).strip() or evidence_item_key(item)
                                for item in (getattr(session, "selected_evidence_payload", []) or [])
                                if isinstance(item, dict)
                            }
                        ),
                        "rejected_chunk_ids": list(
                            {
                                str(item.get("chunk_id", "")).strip() or evidence_item_key(item)
                                for item in (getattr(session, "rejected_evidence_payload", []) or [])
                                if isinstance(item, dict)
                            }
                        ),
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

    async def _plan_retrieval_with_model(self, question_text: str) -> RetrievalPlanResult:
        try:
            planner = get_structured_model(
                schema=RetrievalPlanResult,
                purpose="planning",
            )
            plan = await planner.ainvoke(
                system_prompt=render_prompt_template("classify_and_plan", "system"),
                user_prompt=render_prompt_template("classify_and_plan", "user", question_text=question_text),
                temperature=0,
            )
            logger.debug(
                "Retrieval planning completed via model category=%s strategy=%s",
                plan.question_type,
                plan.retrieval_strategy,
            )
            return plan
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.info("Retrieval planning model unavailable; using heuristic fallback error=%s", exc)
            return retrieval_plan_fallback(question_text)

    async def _classify_with_model(self, question_text: str) -> QuestionClassificationResult:
        """Backward-compatible classifier adapter built on retrieval planning."""

        plan = await self._plan_retrieval_with_model(question_text)
        return QuestionClassificationResult(
            question_type=plan.question_type,
            reasoning_summary=plan.reasoning_summary,
            suggested_retrieval_strategy=plan.retrieval_strategy,
            confidence=plan.confidence,
        )

    def _build_retrieval_config(self, *, plan: RetrievalPlanResult, retry_count: int) -> dict[str, int | str | bool]:
        base_top_k = max(4, int(plan.preferred_top_k or settings.retrieval_top_k))
        if plan.needs_examples:
            base_top_k += 2
        if plan.needs_quantitative_support:
            base_top_k += 2
        if retry_count > 0:
            base_top_k += 4

        base_top_k = min(28, base_top_k)
        strategy = str(plan.retrieval_strategy).strip() or "hybrid"
        if strategy not in {"semantic", "keyword", "hybrid"}:
            strategy = "hybrid"

        semantic_top_k = base_top_k if strategy in {"semantic", "hybrid"} else 0
        keyword_top_k = base_top_k if strategy in {"keyword", "hybrid"} else 0
        if strategy == "hybrid":
            semantic_top_k = max(4, int(round(base_top_k * 0.7)))
            keyword_top_k = max(4, int(round(base_top_k * 0.7)))

        return {
            "strategy": strategy,
            "semantic_top_k": semantic_top_k,
            "keyword_top_k": keyword_top_k,
            "final_top_k": min(32, max(settings.final_evidence_k + 2, base_top_k)),
            "expand_context": bool(plan.should_expand_context or retry_count > 0),
            "context_window": 2 if retry_count > 0 else 1,
            "expand_seed_count": 3 if (plan.needs_examples or retry_count > 0) else 2,
        }

    def _apply_plan_scoring(
        self,
        *,
        chunks: list[dict],
        plan: RetrievalPlanResult,
        retry_count: int,
    ) -> list[dict]:
        deduped: dict[str, dict] = {}
        priorities = [item.strip().lower() for item in plan.priority_sources if isinstance(item, str) and item.strip()]
        if plan.needs_prior_answers and "prior_rfp_answers" not in priorities:
            priorities.append("prior_rfp_answers")
        if plan.question_type and plan.question_type not in priorities:
            priorities.append(str(plan.question_type))

        for chunk in chunks:
            row = {**chunk}
            row_key = evidence_item_key(row)
            boost = 0.0
            if _chunk_matches_priority(row, priorities):
                boost += 0.22
            if plan.needs_examples and _chunk_has_example_signal(row):
                boost += 0.18
            if plan.needs_quantitative_support and _chunk_has_numeric_signal(row):
                boost += 0.18
            if plan.needs_regulatory_context and any(
                token in _chunk_search_blob(row)
                for token in ("regulatory", "regulator", "sfdr", "policy", "compliance")
            ):
                boost += 0.14
            if retry_count > 0 and "context_expand" in str(row.get("retrieval_method", "")):
                boost += 0.08

            base_score = float(row.get("score", 0.0) or 0.0)
            row["score"] = round(base_score + boost, 6)
            row["adaptive_score_boost"] = round(boost, 6)
            current = deduped.get(row_key)
            if current is None or float(row["score"]) > float(current.get("score", 0.0)):
                deduped[row_key] = row

        ranked = sorted(
            deduped.values(),
            key=lambda item: float(item.get("score", 0.0)),
            reverse=True,
        )
        return ranked

    async def _evaluate_evidence_with_model(
        self,
        *,
        question: str,
        plan: RetrievalPlanResult,
        evidence: list[dict],
    ) -> EvidenceEvaluationResult:
        if not evidence:
            return EvidenceEvaluationResult(
                coverage="weak",
                confidence=0.1,
                selected_chunk_ids=[],
                rejected_chunk_ids=[],
                missing_information=["No relevant internal evidence was retrieved."],
                contradictions_found=[],
                evidence_summary="No supporting evidence available for drafting.",
                recommended_action="retrieve_more",
                notes_for_drafting=["Do not assert unsupported facts without retrieval coverage."],
                coverage_by_sub_question={item: "weak" for item in plan.sub_questions[:6]},
                num_supporting_chunks=0,
                num_example_chunks=0,
            )

        sub_questions = "\n".join(f"- {item}" for item in plan.sub_questions[:8]) or "- (none)"
        priority_sources = ", ".join(plan.priority_sources[:8]) or "unspecified"
        try:
            evaluator = get_structured_model(
                schema=EvidenceEvaluationResult,
                purpose="evidence_evaluation",
            )
            return await evaluator.ainvoke(
                system_prompt=render_prompt_template("evaluate_evidence", "system"),
                user_prompt=render_prompt_template(
                    "evaluate_evidence",
                    "user",
                    question_type=plan.question_type,
                    question=question,
                    reasoning_summary=plan.reasoning_summary,
                    sub_questions=sub_questions,
                    priority_sources=priority_sources,
                    needs_examples="yes" if plan.needs_examples else "no",
                    needs_quantitative_support="yes" if plan.needs_quantitative_support else "no",
                    needs_regulatory_context="yes" if plan.needs_regulatory_context else "no",
                    evidence=format_evidence_blob(evidence),
                ),
                temperature=0,
            )
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("Evidence evaluation fallback applied error=%s", exc)

        selected = evidence[: max(settings.final_evidence_k, 4)]
        selected_ids = [evidence_item_key(item) for item in selected]
        example_chunks = [item for item in selected if _chunk_has_example_signal(item)]
        quantitative_chunks = [item for item in selected if _chunk_has_numeric_signal(item)]
        missing: list[str] = []
        if plan.needs_examples and not example_chunks:
            missing.append("Concrete examples/case studies are limited in retrieved evidence.")
        if plan.needs_quantitative_support and not quantitative_chunks:
            missing.append("Quantitative support (metrics/KPIs/capacity) is limited in retrieved evidence.")
        if plan.needs_regulatory_context:
            has_regulatory = any(
                token in _chunk_search_blob(item)
                for item in selected
                for token in ("regulatory", "policy", "sfdr", "compliance")
            )
            if not has_regulatory:
                missing.append("Regulatory/policy context is limited in retrieved evidence.")

        if not missing and len(selected) >= settings.final_evidence_k:
            coverage: Literal["strong", "partial", "weak"] = "strong"
            confidence = 0.82
        elif missing and len(selected) <= 2:
            coverage = "weak"
            confidence = 0.36
        else:
            coverage = "partial"
            confidence = 0.6

        recommended_action: Literal["proceed", "proceed_with_caveats", "retrieve_more"]
        if coverage == "weak":
            recommended_action = "retrieve_more"
        elif coverage == "partial":
            recommended_action = "proceed_with_caveats"
        else:
            recommended_action = "proceed"

        return EvidenceEvaluationResult(
            coverage=coverage,
            confidence=confidence,
            selected_chunk_ids=selected_ids,
            rejected_chunk_ids=[evidence_item_key(item) for item in evidence[len(selected):]],
            missing_information=missing,
            contradictions_found=[],
            evidence_summary=(
                f"Fallback evidence evaluation retained {len(selected)} chunk(s) for drafting with {coverage} coverage."
            ),
            recommended_action=recommended_action,
            notes_for_drafting=(
                [
                    "Use cautious language and acknowledge evidence limits where needed.",
                    *[f"Gap to acknowledge: {item}" for item in missing],
                ]
                if missing
                else ["Evidence appears sufficient for a grounded draft."]
            ),
            coverage_by_sub_question={item: coverage for item in plan.sub_questions[:6]},
            num_supporting_chunks=len(selected),
            num_example_chunks=len(example_chunks),
        )

    def _normalize_evaluation_result(
        self,
        *,
        evaluation: EvidenceEvaluationResult,
        evidence: list[dict],
        plan: RetrievalPlanResult,
    ) -> EvidenceEvaluationResult:
        valid_ids = {evidence_item_key(item) for item in evidence}
        selected_ids = [item.strip() for item in evaluation.selected_chunk_ids if item.strip() in valid_ids]
        rejected_ids = [item.strip() for item in evaluation.rejected_chunk_ids if item.strip() in valid_ids]

        if not selected_ids and evidence:
            selected_ids = [evidence_item_key(item) for item in evidence[: max(settings.final_evidence_k, 4)]]
        rejected_ids = [item for item in rejected_ids if item not in selected_ids]

        num_example = 0
        num_supporting = 0
        for item in evidence:
            key = evidence_item_key(item)
            if key not in selected_ids:
                continue
            num_supporting += 1
            if _chunk_has_example_signal(item):
                num_example += 1

        coverage_by_sub_question = dict(evaluation.coverage_by_sub_question or {})
        if not coverage_by_sub_question and plan.sub_questions:
            coverage_by_sub_question = {item: evaluation.coverage for item in plan.sub_questions[:6]}

        return evaluation.model_copy(
            update={
                "selected_chunk_ids": selected_ids,
                "rejected_chunk_ids": rejected_ids,
                "num_supporting_chunks": num_supporting,
                "num_example_chunks": num_example,
                "coverage_by_sub_question": coverage_by_sub_question,
            }
        )

    def _partition_evidence(
        self,
        *,
        evidence: list[dict],
        selected_ids: list[str],
        rejected_ids: list[str],
    ) -> tuple[list[dict], list[dict], list[dict]]:
        selected_lookup = {item.strip() for item in selected_ids if item.strip()}
        rejected_lookup = {item.strip() for item in rejected_ids if item.strip()}
        selected: list[dict] = []
        rejected: list[dict] = []
        annotated: list[dict] = []

        for item in evidence:
            row = {**item}
            key = evidence_item_key(row)
            is_selected = key in selected_lookup
            is_rejected = key in rejected_lookup and not is_selected
            row["selected_for_drafting"] = is_selected
            row["rejected_by_evaluator"] = is_rejected
            if is_selected:
                selected.append(row)
            elif is_rejected:
                rejected.append(row)
            annotated.append(row)

        if not selected and evidence:
            default_selected = {evidence_item_key(item) for item in evidence[: max(settings.final_evidence_k, 4)]}
            selected = []
            rejected = []
            annotated = []
            for item in evidence:
                row = {**item}
                key = evidence_item_key(row)
                is_selected = key in default_selected
                row["selected_for_drafting"] = is_selected
                row["rejected_by_evaluator"] = not is_selected
                if is_selected:
                    selected.append(row)
                else:
                    rejected.append(row)
                annotated.append(row)

        return selected, rejected, annotated

    def _augment_plan_for_retry(
        self,
        *,
        plan: RetrievalPlanResult,
        evaluation: EvidenceEvaluationResult,
    ) -> RetrievalPlanResult:
        priority_sources = [
            item.strip()
            for item in plan.priority_sources
            if isinstance(item, str) and item.strip()
        ]
        additions: list[str] = []
        if plan.needs_examples:
            additions.append("portfolio_examples")
        if plan.needs_quantitative_support:
            additions.append("performance_metrics")
        if plan.needs_regulatory_context:
            additions.append("regulatory_policy")
        if plan.needs_prior_answers:
            additions.append("prior_rfp_answers")
        if any("contradiction" in item.lower() for item in evaluation.notes_for_drafting):
            additions.append("governance_policy")
        for item in additions:
            if item not in priority_sources:
                priority_sources.append(item)

        updated_reasoning = (
            f"{plan.reasoning_summary.strip()} "
            f"Retry retrieval targeted missing info: {'; '.join(evaluation.missing_information[:3])}."
        ).strip()
        return plan.model_copy(
            update={
                "priority_sources": priority_sources,
                "should_expand_context": True,
                "preferred_top_k": min(24, max(plan.preferred_top_k + 4, settings.retrieval_top_k + 2)),
                "reasoning_summary": updated_reasoning,
                "confidence": max(0.0, min(1.0, float(plan.confidence) * 0.9)),
            }
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
        retrieval_plan: dict | None = None,
        evidence_evaluation: dict | None = None,
        retrieval_strategy_used: str | None = None,
    ) -> tuple[str, str, dict, dict]:
        if not evidence:
            logger.warning("Draft requested without evidence; returning low-confidence response")
            evaluation_obj = (
                EvidenceEvaluationResult.model_validate(evidence_evaluation or {})
                if evidence_evaluation
                else None
            )
            confidence_payload = build_structured_confidence_payload(
                evaluation=evaluation_obj,
                retrieval_strategy_used=retrieval_strategy_used,
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
        evaluation_obj = (
            EvidenceEvaluationResult.model_validate(evidence_evaluation or {})
            if evidence_evaluation
            else None
        )
        plan_obj = RetrievalPlanResult.model_validate(retrieval_plan or {}) if retrieval_plan else None
        retrieval_plan_summary = "No explicit retrieval plan was provided."
        if plan_obj:
            sub_q = "; ".join(plan_obj.sub_questions[:4]) or "No explicit sub-questions."
            priorities = ", ".join(plan_obj.priority_sources[:5]) or "unspecified"
            retrieval_plan_summary = (
                f"{plan_obj.reasoning_summary} "
                f"Sub-questions: {sub_q}. "
                f"Priority sources: {priorities}. "
                f"Strategy: {plan_obj.retrieval_strategy}."
            ).strip()
        evidence_notes = "No explicit evaluator notes were provided."
        if evaluation_obj:
            notes = "; ".join(evaluation_obj.notes_for_drafting[:6])
            evidence_notes = (
                f"Coverage={evaluation_obj.coverage}; "
                f"recommended_action={evaluation_obj.recommended_action}; "
                f"{notes or 'Use selected evidence only.'}"
            )

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
                    retrieval_plan_summary=retrieval_plan_summary,
                    evidence_notes_for_drafting=evidence_notes,
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
                evaluation=evaluation_obj,
                retrieval_strategy_used=retrieval_strategy_used,
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
                evaluation=evaluation_obj,
                retrieval_strategy_used=retrieval_strategy_used,
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
