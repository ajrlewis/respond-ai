"""SQLAlchemy models for RespondAI."""

import uuid
from datetime import datetime

from pgvector.sqlalchemy import Vector
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.dialects.postgresql import JSONB, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

from app.core.config import settings


class Base(DeclarativeBase):
    """Base declarative model."""


class Document(Base):
    """Represents a source document used for retrieval."""

    __tablename__ = "documents"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    filename: Mapped[str] = mapped_column(String(255), nullable=False, unique=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    source_type: Mapped[str] = mapped_column(String(50), nullable=False, default="internal_markdown")
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    chunks: Mapped[list["DocumentChunk"]] = relationship(
        back_populates="document",
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class DocumentChunk(Base):
    """Chunked document section with embedding vector."""

    __tablename__ = "document_chunks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    document_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    chunk_text: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    embedding: Mapped[list[float]] = mapped_column(Vector(settings.embedding_dimension), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    document: Mapped[Document] = relationship(back_populates="chunks")


class RFPSession(Base):
    """Business workflow session for an RFP question."""

    __tablename__ = "rfp_sessions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_thread_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    question_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    tone: Mapped[str] = mapped_column(String(32), nullable=False, default="formal")
    status: Mapped[str] = mapped_column(String(64), nullable=False, default="draft")
    current_node: Mapped[str | None] = mapped_column(String(64), nullable=True)
    draft_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_version_number: Mapped[int | None] = mapped_column(Integer, nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewer_action: Mapped[str | None] = mapped_column(String(32), nullable=True)
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    evidence_gaps_acknowledged: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_gaps_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    confidence_notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confidence_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    evidence_payload: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    answer_versions_payload: Mapped[list[dict]] = mapped_column(JSONB, default=list)
    final_audit_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    reviews: Mapped[list["RFPReview"]] = relationship(
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by="RFPReview.created_at",
    )


class RFPReview(Base):
    """Review actions applied by human reviewers."""

    __tablename__ = "rfp_reviews"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfp_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    reviewer_action: Mapped[str] = mapped_column(String(32), nullable=False)
    reviewer_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    review_comments: Mapped[str | None] = mapped_column(Text, nullable=True)
    edited_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    excluded_evidence_keys: Mapped[list[str]] = mapped_column(JSONB, default=list)
    reviewed_evidence_gaps: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    evidence_gaps_acknowledged_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    session: Mapped[RFPSession] = relationship(back_populates="reviews")


class GraphRun(Base):
    """Represents one workflow execution attempt."""

    __tablename__ = "graph_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfp_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    thread_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    graph_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    large_model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    small_model_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    embedding_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class NodeRun(Base):
    """Represents execution telemetry for a graph node."""

    __tablename__ = "node_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfp_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    duration_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    input_state_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    output_state_summary: Mapped[dict] = mapped_column(JSONB, default=dict)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class ToolRun(Base):
    """Represents one retrieval/tool invocation during a graph run."""

    __tablename__ = "tool_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    graph_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("node_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfp_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(128), nullable=False)
    tool_type: Mapped[str] = mapped_column(String(64), nullable=False)
    query_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    arguments_json: Mapped[dict] = mapped_column("arguments", JSONB, default=dict)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    result_ids: Mapped[list[str]] = mapped_column(JSONB, default=list)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)


class LLMCall(Base):
    """Represents one LLM or embedding API call."""

    __tablename__ = "llm_calls"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfp_sessions.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    draft_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    graph_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("graph_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    node_run_id: Mapped[uuid.UUID | None] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("node_runs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(64), nullable=False, default="openai")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    call_type: Mapped[str] = mapped_column(String(64), nullable=False)
    purpose: Mapped[str] = mapped_column(String(128), nullable=False, default="unspecified")
    request_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    response_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_input_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    normalized_output_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    raw_usage_payload: Mapped[dict] = mapped_column(JSONB, default=dict)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="success")
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class SessionMetric(Base):
    """Session-level aggregate metrics for observability and evals."""

    __tablename__ = "session_metrics"
    __table_args__ = (UniqueConstraint("session_id", name="uq_session_metrics_session_id"),)

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfp_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    latest_draft_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    approved_draft_id: Mapped[str | None] = mapped_column(String(128), nullable=True)
    question_type: Mapped[str | None] = mapped_column(String(64), nullable=True)
    num_retrieved_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_cited_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_uncited_chunks: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    num_revision_rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    approved: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    time_to_first_draft_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    time_to_approval_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    total_llm_calls: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    total_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estimated_cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class EvalRun(Base):
    """Represents one evaluation execution against historical sessions."""

    __tablename__ = "eval_runs"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="running")
    target_session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    evaluated_session_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    average_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column("metadata", JSONB, default=dict)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)


class EvalResult(Base):
    """Metric-level evaluation score for a single session within an eval run."""

    __tablename__ = "eval_results"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    eval_run_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("eval_runs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    session_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("rfp_sessions.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    metric_name: Mapped[str] = mapped_column(String(128), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    passed: Mapped[bool] = mapped_column(Boolean, nullable=False)
    details: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
