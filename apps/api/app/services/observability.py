"""Observability helpers for graph execution, model usage, and eval telemetry."""

from __future__ import annotations

from collections.abc import Mapping
from contextvars import ContextVar, Token
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
import hashlib
import json
import logging
from typing import Any
import uuid

from sqlalchemy import case, func, select

from app.core.config import settings
from app.core.database import AsyncSessionLocal, SessionLocal
from app.db.models import GraphRun, LLMCall, NodeRun, RFPReview, RFPSession, SessionMetric, ToolRun
from app.services.draft_history import list_session_drafts

logger = logging.getLogger(__name__)


DEFAULT_MODEL_PRICING: dict[str, dict[str, float]] = {
    "gpt-4o": {"input_per_1k": 0.005, "output_per_1k": 0.015},
    "gpt-4o-mini": {"input_per_1k": 0.00015, "output_per_1k": 0.0006},
    "text-embedding-3-small": {"input_per_1k": 0.00002, "output_per_1k": 0.0},
    "text-embedding-3-large": {"input_per_1k": 0.00013, "output_per_1k": 0.0},
}


@dataclass(frozen=True)
class ObservabilityContext:
    """Context propagated across graph/node/model/tool calls."""

    session_id: str | None = None
    draft_id: str | None = None
    graph_run_id: str | None = None
    node_run_id: str | None = None
    graph_name: str | None = None
    node_name: str | None = None


_CONTEXT: ContextVar[ObservabilityContext] = ContextVar("respondai_observability_context", default=ObservabilityContext())


def get_observability_context() -> ObservabilityContext:
    """Return the active observability context."""

    return _CONTEXT.get()


def set_observability_context(**kwargs: str | None) -> Token[ObservabilityContext]:
    """Merge context values and return token for reset."""

    current = asdict(_CONTEXT.get())
    for key, value in kwargs.items():
        if key not in current:
            continue
        current[key] = str(value).strip() if value else None
    return _CONTEXT.set(ObservabilityContext(**current))


def reset_observability_context(token: Token[ObservabilityContext]) -> None:
    """Reset a previously-set context token."""

    _CONTEXT.reset(token)


def push_node_context(*, session_id: str | None, node_run_id: str | None, node_name: str) -> Token[ObservabilityContext]:
    """Push node-specific context while preserving graph-level metadata."""

    current = _CONTEXT.get()
    updated = replace(
        current,
        session_id=(str(session_id).strip() if session_id else current.session_id),
        node_run_id=(str(node_run_id).strip() if node_run_id else current.node_run_id),
        node_name=node_name,
    )
    return _CONTEXT.set(updated)


@dataclass(slots=True)
class LLMLogRecord:
    """Normalized model-call payload for persistence."""

    provider: str
    model_name: str
    call_type: str
    purpose: str
    request_payload: dict
    response_payload: dict
    input_tokens: int
    output_tokens: int
    total_tokens: int
    estimated_cost_usd: float | None
    latency_ms: int | None
    status: str
    error_message: str | None
    session_id: str | None = None
    draft_id: str | None = None
    graph_run_id: str | None = None
    node_run_id: str | None = None
    normalized_input_tokens: int = 0
    normalized_output_tokens: int = 0
    raw_usage_payload: dict | None = None


def _coerce_uuid(value: str | uuid.UUID | None) -> uuid.UUID | None:
    if value is None:
        return None
    if isinstance(value, uuid.UUID):
        return value
    text = str(value).strip()
    if not text:
        return None
    try:
        return uuid.UUID(text)
    except ValueError:
        return None


def _sanitize_json(value: Any, *, depth: int = 0, max_depth: int = 4) -> Any:
    if depth >= max_depth:
        return "<trimmed>"

    if value is None or isinstance(value, (bool, int, float)):
        return value

    if isinstance(value, str):
        trimmed = value.strip()
        if len(trimmed) > 8000:
            return f"{trimmed[:8000]}...<trimmed:{len(trimmed) - 8000}>"
        return trimmed

    if isinstance(value, Mapping):
        output: dict[str, Any] = {}
        for index, (key, nested) in enumerate(value.items()):
            if index >= 40:
                output["_trimmed"] = f"additional_keys={len(value) - 40}"
                break
            output[str(key)] = _sanitize_json(nested, depth=depth + 1, max_depth=max_depth)
        return output

    if isinstance(value, list):
        rows = [_sanitize_json(item, depth=depth + 1, max_depth=max_depth) for item in value[:40]]
        if len(value) > 40:
            rows.append(f"<trimmed:{len(value) - 40}>")
        return rows

    if isinstance(value, tuple):
        return [_sanitize_json(item, depth=depth + 1, max_depth=max_depth) for item in value[:40]]

    if hasattr(value, "model_dump"):
        return _sanitize_json(value.model_dump(), depth=depth + 1, max_depth=max_depth)

    return str(value)


def sanitize_payload(payload: Any) -> dict:
    """Sanitize request/response payloads for persistence."""

    normalized = _sanitize_json(payload)
    if isinstance(normalized, dict):
        return normalized
    return {"value": normalized}


def load_model_pricing() -> dict[str, dict[str, float]]:
    """Load per-model cost rates, allowing env overrides."""

    configured = settings.model_pricing_json.strip()
    if not configured:
        return DEFAULT_MODEL_PRICING

    try:
        data = json.loads(configured)
    except json.JSONDecodeError:
        logger.warning("Failed to parse MODEL_PRICING_JSON; using defaults")
        return DEFAULT_MODEL_PRICING

    if not isinstance(data, dict):
        logger.warning("MODEL_PRICING_JSON must be an object; using defaults")
        return DEFAULT_MODEL_PRICING

    merged = dict(DEFAULT_MODEL_PRICING)
    for model_name, row in data.items():
        if not isinstance(row, dict):
            continue
        input_rate = row.get("input_per_1k")
        output_rate = row.get("output_per_1k")
        if isinstance(input_rate, (int, float)) and isinstance(output_rate, (int, float)):
            merged[str(model_name)] = {
                "input_per_1k": float(input_rate),
                "output_per_1k": float(output_rate),
            }
    return merged


def estimate_cost_usd(*, model_name: str, input_tokens: int, output_tokens: int) -> float | None:
    """Estimate call cost in USD from token counts and configured model rates."""

    rates = load_model_pricing().get(model_name)
    if not rates:
        return None

    input_cost = (max(0, int(input_tokens)) / 1000) * float(rates["input_per_1k"])
    output_cost = (max(0, int(output_tokens)) / 1000) * float(rates["output_per_1k"])
    return round(input_cost + output_cost, 8)


def extract_token_usage(response: Any) -> tuple[int, int, int]:
    """Extract token usage from OpenAI responses."""

    usage = getattr(response, "usage", None)
    if usage is None and isinstance(response, dict):
        usage = response.get("usage")

    prompt_tokens = 0
    completion_tokens = 0
    total_tokens = 0

    if usage is not None:
        prompt_tokens = int(getattr(usage, "prompt_tokens", 0) or 0)
        completion_tokens = int(getattr(usage, "completion_tokens", 0) or 0)
        total_tokens = int(getattr(usage, "total_tokens", 0) or 0)

        if isinstance(usage, dict):
            prompt_tokens = int(usage.get("prompt_tokens", prompt_tokens) or 0)
            completion_tokens = int(usage.get("completion_tokens", completion_tokens) or 0)
            total_tokens = int(usage.get("total_tokens", total_tokens) or 0)

    if total_tokens <= 0:
        total_tokens = max(0, prompt_tokens) + max(0, completion_tokens)

    return max(0, prompt_tokens), max(0, completion_tokens), max(0, total_tokens)


def _apply_context(record: LLMLogRecord) -> LLMLogRecord:
    context = get_observability_context()
    return replace(
        record,
        session_id=record.session_id or context.session_id,
        draft_id=record.draft_id or context.draft_id,
        graph_run_id=record.graph_run_id or context.graph_run_id,
        node_run_id=record.node_run_id or context.node_run_id,
    )


async def log_llm_call_async(record: LLMLogRecord) -> None:
    """Persist one LLM/embedding invocation asynchronously."""

    row = _apply_context(record)
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                LLMCall(
                    session_id=_coerce_uuid(row.session_id),
                    draft_id=row.draft_id,
                    graph_run_id=_coerce_uuid(row.graph_run_id),
                    node_run_id=_coerce_uuid(row.node_run_id),
                    provider=row.provider,
                    model_name=row.model_name,
                    call_type=row.call_type,
                    purpose=row.purpose,
                    request_payload=sanitize_payload(row.request_payload),
                    response_payload=sanitize_payload(row.response_payload),
                    input_tokens=max(0, int(row.input_tokens)),
                    output_tokens=max(0, int(row.output_tokens)),
                    total_tokens=max(0, int(row.total_tokens)),
                    normalized_input_tokens=max(0, int(row.normalized_input_tokens)),
                    normalized_output_tokens=max(0, int(row.normalized_output_tokens)),
                    raw_usage_payload=sanitize_payload(row.raw_usage_payload or {}),
                    estimated_cost_usd=row.estimated_cost_usd,
                    latency_ms=row.latency_ms,
                    status=row.status,
                    error_message=(row.error_message or "").strip() or None,
                )
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to persist async llm call telemetry: %s", exc)


def log_llm_call_sync(record: LLMLogRecord) -> None:
    """Persist one LLM/embedding invocation synchronously."""

    row = _apply_context(record)
    try:
        with SessionLocal() as db:
            db.add(
                LLMCall(
                    session_id=_coerce_uuid(row.session_id),
                    draft_id=row.draft_id,
                    graph_run_id=_coerce_uuid(row.graph_run_id),
                    node_run_id=_coerce_uuid(row.node_run_id),
                    provider=row.provider,
                    model_name=row.model_name,
                    call_type=row.call_type,
                    purpose=row.purpose,
                    request_payload=sanitize_payload(row.request_payload),
                    response_payload=sanitize_payload(row.response_payload),
                    input_tokens=max(0, int(row.input_tokens)),
                    output_tokens=max(0, int(row.output_tokens)),
                    total_tokens=max(0, int(row.total_tokens)),
                    normalized_input_tokens=max(0, int(row.normalized_input_tokens)),
                    normalized_output_tokens=max(0, int(row.normalized_output_tokens)),
                    raw_usage_payload=sanitize_payload(row.raw_usage_payload or {}),
                    estimated_cost_usd=row.estimated_cost_usd,
                    latency_ms=row.latency_ms,
                    status=row.status,
                    error_message=(row.error_message or "").strip() or None,
                )
            )
            db.commit()
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to persist sync llm call telemetry: %s", exc)


async def create_graph_run(
    *,
    graph_name: str,
    thread_id: str | None,
    session_id: str | None,
    metadata: dict | None = None,
) -> uuid.UUID | None:
    """Create a graph run record and return its id."""

    try:
        async with AsyncSessionLocal() as db:
            row = GraphRun(
                graph_name=graph_name,
                thread_id=(thread_id or "").strip() or None,
                session_id=_coerce_uuid(session_id),
                status="running",
                metadata_json=sanitize_payload(metadata or {}),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row.id
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to create graph run telemetry row: %s", exc)
        return None


async def finalize_graph_run(
    graph_run_id: str | uuid.UUID | None,
    *,
    status: str,
    session_id: str | None = None,
    metadata: dict | None = None,
    error_message: str | None = None,
) -> None:
    """Finalize graph run with aggregates from logged model usage."""

    parsed_id = _coerce_uuid(graph_run_id)
    if not parsed_id:
        return

    completed_at = datetime.now(UTC)
    try:
        async with AsyncSessionLocal() as db:
            graph_run = await db.get(GraphRun, parsed_id)
            if not graph_run:
                return

            usage_row = (
                await db.execute(
                    select(
                        func.count(LLMCall.id),
                        func.coalesce(func.sum(LLMCall.input_tokens), 0),
                        func.coalesce(func.sum(LLMCall.output_tokens), 0),
                        func.coalesce(func.sum(LLMCall.total_tokens), 0),
                        func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0.0),
                        func.coalesce(
                            func.sum(case((LLMCall.model_name == settings.large_llm_model, 1), else_=0)),
                            0,
                        ),
                        func.coalesce(
                            func.sum(case((LLMCall.model_name == settings.small_llm_model, 1), else_=0)),
                            0,
                        ),
                        func.coalesce(func.sum(case((LLMCall.call_type == "embedding", 1), else_=0)), 0),
                    ).where(LLMCall.graph_run_id == parsed_id)
                )
            ).one()

            graph_run.status = status
            graph_run.completed_at = completed_at
            if graph_run.started_at:
                graph_run.duration_ms = max(
                    0,
                    int((completed_at - graph_run.started_at).total_seconds() * 1000),
                )
            graph_run.session_id = _coerce_uuid(session_id) or graph_run.session_id
            graph_run.total_input_tokens = int(usage_row[1] or 0)
            graph_run.total_output_tokens = int(usage_row[2] or 0)
            graph_run.total_tokens = int(usage_row[3] or 0)
            graph_run.estimated_cost_usd = float(usage_row[4]) if usage_row[4] is not None else None
            graph_run.large_model_calls = int(usage_row[5] or 0)
            graph_run.small_model_calls = int(usage_row[6] or 0)
            graph_run.embedding_calls = int(usage_row[7] or 0)
            graph_run.error_message = (error_message or "").strip() or None
            if metadata:
                merged_metadata = dict(graph_run.metadata_json or {})
                merged_metadata.update(sanitize_payload(metadata))
                graph_run.metadata_json = merged_metadata

            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to finalize graph run telemetry row: %s", exc)


async def create_node_run(
    *,
    graph_run_id: str | None,
    session_id: str | None,
    node_name: str,
    input_state_summary: dict,
    metadata: dict | None = None,
) -> uuid.UUID | None:
    """Create a node run row and return id."""

    try:
        async with AsyncSessionLocal() as db:
            row = NodeRun(
                graph_run_id=_coerce_uuid(graph_run_id),
                session_id=_coerce_uuid(session_id),
                node_name=node_name,
                status="running",
                input_state_summary=sanitize_payload(input_state_summary),
                metadata_json=sanitize_payload(metadata or {}),
            )
            db.add(row)
            await db.commit()
            await db.refresh(row)
            return row.id
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to create node run telemetry row: %s", exc)
        return None


async def finalize_node_run(
    node_run_id: str | uuid.UUID | None,
    *,
    status: str,
    output_state_summary: dict,
    session_id: str | None = None,
    error_message: str | None = None,
) -> None:
    """Finalize a node run with output summary and timing."""

    parsed_id = _coerce_uuid(node_run_id)
    if not parsed_id:
        return

    completed_at = datetime.now(UTC)
    try:
        async with AsyncSessionLocal() as db:
            row = await db.get(NodeRun, parsed_id)
            if not row:
                return

            row.status = status
            row.session_id = _coerce_uuid(session_id) or row.session_id
            row.completed_at = completed_at
            if row.started_at:
                row.duration_ms = max(0, int((completed_at - row.started_at).total_seconds() * 1000))
            row.output_state_summary = sanitize_payload(output_state_summary)
            row.error_message = (error_message or "").strip() or None
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to finalize node run telemetry row: %s", exc)


async def log_tool_run(
    *,
    tool_name: str,
    tool_type: str,
    query_text: str | None,
    arguments: dict,
    result_ids: list[str],
    result_count: int,
    latency_ms: int,
    status: str,
    metadata: dict | None = None,
    graph_run_id: str | None = None,
    node_run_id: str | None = None,
    session_id: str | None = None,
) -> None:
    """Persist one tool/retrieval invocation."""

    context = get_observability_context()
    try:
        async with AsyncSessionLocal() as db:
            db.add(
                ToolRun(
                    graph_run_id=_coerce_uuid(graph_run_id or context.graph_run_id),
                    node_run_id=_coerce_uuid(node_run_id or context.node_run_id),
                    session_id=_coerce_uuid(session_id or context.session_id),
                    tool_name=tool_name,
                    tool_type=tool_type,
                    query_text=(query_text or "").strip() or None,
                    arguments_json=sanitize_payload(arguments),
                    result_count=max(0, int(result_count)),
                    result_ids=[str(item) for item in result_ids],
                    latency_ms=max(0, int(latency_ms)),
                    status=status,
                    metadata_json=sanitize_payload(metadata or {}),
                )
            )
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to persist tool run telemetry: %s", exc)


def summarize_workflow_state(state: Mapping[str, Any]) -> dict:
    """Build compact, eval-friendly summaries for node input/output state."""

    question_text = str(state.get("question_text", "")).strip()
    question_hash = hashlib.sha256(question_text.encode("utf-8")).hexdigest()[:16] if question_text else None

    confidence_payload = state.get("confidence_payload")
    if isinstance(confidence_payload, dict):
        confidence_score = confidence_payload.get("score")
        evidence_gaps = confidence_payload.get("evidence_gaps", [])
        coverage = confidence_payload.get("coverage")
        recommended_action = confidence_payload.get("recommended_action")
    else:
        confidence_score = None
        evidence_gaps = []
        coverage = None
        recommended_action = None

    summary = {
        "session_id": str(state.get("session_id", "") or "").strip() or None,
        "thread_id": str(state.get("thread_id", "") or "").strip() or None,
        "question_excerpt": question_text[:200] if question_text else None,
        "question_hash": question_hash,
        "question_type": state.get("question_type"),
        "tone": state.get("tone"),
        "status": state.get("status"),
        "current_node": state.get("current_node"),
        "review_action": state.get("review_action"),
        "retrieved_evidence_count": len(state.get("retrieved_evidence", []) or []),
        "retrieved_chunks_count": len(state.get("retrieved_chunks", []) or []),
        "curated_evidence_count": len(state.get("curated_evidence", []) or []),
        "selected_evidence_count": len(state.get("selected_evidence", []) or []),
        "rejected_evidence_count": len(state.get("rejected_evidence", []) or []),
        "excluded_evidence_count": len(state.get("excluded_evidence_keys", []) or []),
        "answer_versions_count": len(state.get("answer_versions", []) or []),
        "draft_chars": len(str(state.get("draft_answer", "") or "")),
        "final_chars": len(str(state.get("final_answer", "") or "")),
        "confidence_score": confidence_score if isinstance(confidence_score, (int, float)) else None,
        "evidence_gap_count": len([item for item in evidence_gaps if isinstance(item, str) and item.strip()]),
        "coverage": coverage if isinstance(coverage, str) else None,
        "recommended_action": recommended_action if isinstance(recommended_action, str) else None,
        "retrieval_strategy_used": state.get("retrieval_strategy_used"),
        "retry_count": int(state.get("retry_count", 0) or 0),
    }
    return sanitize_payload(summary)


def determine_graph_status(result: Any, *, default_status: str) -> str:
    """Infer graph run status from a graph invoke result payload."""

    if isinstance(result, Mapping):
        state_status = str(result.get("status", "")).strip().lower()
        current_node = str(result.get("current_node", "")).strip().lower()

        if state_status in {"error", "failed"}:
            return "error"

        if state_status == "approved" or bool(result.get("final_answer")):
            return "completed"

        if state_status in {"awaiting_review", "awaiting_finalization", "revision_requested"}:
            return "paused_for_review"

        if current_node == "human_review":
            return "paused_for_review"

    return default_status


async def refresh_session_metrics(session_id: str | uuid.UUID | None) -> None:
    """Upsert aggregate session metrics from persisted telemetry."""

    parsed_session_id = _coerce_uuid(session_id)
    if not parsed_session_id:
        return

    try:
        async with AsyncSessionLocal() as db:
            session = await db.get(RFPSession, parsed_session_id)
            if not session:
                return

            drafts = list_session_drafts(session)
            latest_draft = drafts[-1] if drafts else None
            latest_draft_id = str(latest_draft.get("version_id")) if latest_draft else None
            approved_draft_id = latest_draft_id if getattr(session, "status", "") == "approved" else None

            retrieved_chunks = list(getattr(session, "evidence_payload", []) or [])
            num_retrieved_chunks = len(retrieved_chunks)

            included_chunk_ids: list[str] = []
            if isinstance(getattr(session, "final_audit_payload", None), dict):
                included = session.final_audit_payload.get("included_chunk_ids", [])
                if isinstance(included, list):
                    included_chunk_ids = [str(item) for item in included]

            if not included_chunk_ids and latest_draft:
                included = latest_draft.get("included_chunk_ids", [])
                if isinstance(included, list):
                    included_chunk_ids = [str(item) for item in included]

            num_cited_chunks = len({item for item in included_chunk_ids if item.strip()})
            num_uncited_chunks = max(0, num_retrieved_chunks - num_cited_chunks)

            revision_count = int(
                (
                    await db.execute(
                        select(func.count(RFPReview.id)).where(
                            RFPReview.session_id == parsed_session_id,
                            RFPReview.reviewer_action == "revise",
                        )
                    )
                ).scalar_one()
                or 0
            )

            llm_agg = (
                await db.execute(
                    select(
                        func.count(LLMCall.id),
                        func.coalesce(func.sum(LLMCall.total_tokens), 0),
                        func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0.0),
                    ).where(LLMCall.session_id == parsed_session_id)
                )
            ).one()
            total_llm_calls = int(llm_agg[0] or 0)
            total_tokens = int(llm_agg[1] or 0)
            estimated_cost = float(llm_agg[2]) if llm_agg[2] is not None else None

            first_draft_started = (
                await db.execute(
                    select(NodeRun.started_at)
                    .where(
                        NodeRun.session_id == parsed_session_id,
                        NodeRun.node_name == "draft_response",
                        NodeRun.status == "success",
                    )
                    .order_by(NodeRun.started_at.asc())
                    .limit(1)
                )
            ).scalar_one_or_none()

            time_to_first_draft_ms: int | None = None
            if first_draft_started and session.created_at:
                time_to_first_draft_ms = max(
                    0,
                    int((first_draft_started - session.created_at).total_seconds() * 1000),
                )

            time_to_approval_ms: int | None = None
            if getattr(session, "approved_at", None) and session.created_at:
                time_to_approval_ms = max(
                    0,
                    int((session.approved_at - session.created_at).total_seconds() * 1000),
                )

            row = (
                await db.execute(select(SessionMetric).where(SessionMetric.session_id == parsed_session_id))
            ).scalar_one_or_none()
            if row is None:
                row = SessionMetric(session_id=parsed_session_id)
                db.add(row)

            row.latest_draft_id = latest_draft_id
            row.approved_draft_id = approved_draft_id
            row.question_type = session.question_type
            row.num_retrieved_chunks = num_retrieved_chunks
            row.num_cited_chunks = num_cited_chunks
            row.num_uncited_chunks = num_uncited_chunks
            row.num_revision_rounds = revision_count
            row.approved = getattr(session, "status", "") == "approved"
            row.time_to_first_draft_ms = time_to_first_draft_ms
            row.time_to_approval_ms = time_to_approval_ms
            row.total_llm_calls = total_llm_calls
            row.total_tokens = total_tokens
            row.estimated_cost_usd = estimated_cost
            row.metadata_json = {
                "session_status": session.status,
                "final_version_number": getattr(session, "final_version_number", None),
                "retrieval_strategy_used": getattr(session, "retrieval_strategy_used", None),
                "retry_count": int(getattr(session, "retry_count", 0) or 0),
                "coverage": (
                    (getattr(session, "evidence_evaluation_payload", {}) or {}).get("coverage")
                    if isinstance(getattr(session, "evidence_evaluation_payload", {}), dict)
                    else None
                ),
            }
            await db.commit()
    except Exception as exc:  # pragma: no cover - defensive telemetry path
        logger.warning("Failed to refresh session metrics session_id=%s error=%s", parsed_session_id, exc)
