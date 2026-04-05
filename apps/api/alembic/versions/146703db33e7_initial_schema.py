"""initial schema

Revision ID: 146703db33e7
Revises: 
Create Date: 2026-04-05 10:45:09.803764

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import Vector
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '146703db33e7'
down_revision: Union[str, Sequence[str], None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")

    op.create_table(
        "documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_type", sa.String(length=50), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("filename"),
    )

    op.create_table(
        "rfp_sessions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_thread_id", sa.String(length=128), nullable=False),
        sa.Column("question_text", sa.Text(), nullable=False),
        sa.Column("question_type", sa.String(length=64), nullable=True),
        sa.Column("tone", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=64), nullable=False),
        sa.Column("current_node", sa.String(length=64), nullable=True),
        sa.Column("retrieval_strategy_used", sa.String(length=32), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("draft_answer", sa.Text(), nullable=True),
        sa.Column("final_answer", sa.Text(), nullable=True),
        sa.Column("final_version_number", sa.Integer(), nullable=True),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewer_action", sa.String(length=32), nullable=True),
        sa.Column("reviewer_id", sa.String(length=128), nullable=True),
        sa.Column("evidence_gaps_acknowledged", sa.Boolean(), nullable=False),
        sa.Column("evidence_gaps_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("confidence_notes", sa.Text(), nullable=True),
        sa.Column("confidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieval_plan_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("retrieval_metadata_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_evaluation_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("selected_evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("rejected_evidence_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("answer_versions_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("final_audit_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rfp_sessions_graph_thread_id", "rfp_sessions", ["graph_thread_id"], unique=True)

    op.create_table(
        "eval_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("target_session_count", sa.Integer(), nullable=False),
        sa.Column("evaluated_session_count", sa.Integer(), nullable=False),
        sa.Column("average_score", sa.Float(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "document_chunks",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("chunk_index", sa.Integer(), nullable=False),
        sa.Column("chunk_text", sa.Text(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("embedding", Vector(dim=1536), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["document_id"], ["documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_document_chunks_document_id", "document_chunks", ["document_id"], unique=False)

    op.create_table(
        "rfp_reviews",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("reviewer_action", sa.String(length=32), nullable=False),
        sa.Column("reviewer_id", sa.String(length=128), nullable=True),
        sa.Column("review_comments", sa.Text(), nullable=True),
        sa.Column("edited_answer", sa.Text(), nullable=True),
        sa.Column("excluded_evidence_keys", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("reviewed_evidence_gaps", sa.Boolean(), nullable=False),
        sa.Column("evidence_gaps_acknowledged_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["rfp_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_rfp_reviews_session_id", "rfp_reviews", ["session_id"], unique=False)

    op.create_table(
        "graph_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("thread_id", sa.String(length=128), nullable=True),
        sa.Column("graph_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("large_model_calls", sa.Integer(), nullable=False),
        sa.Column("small_model_calls", sa.Integer(), nullable=False),
        sa.Column("embedding_calls", sa.Integer(), nullable=False),
        sa.Column("total_input_tokens", sa.Integer(), nullable=False),
        sa.Column("total_output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["session_id"], ["rfp_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_graph_runs_session_id", "graph_runs", ["session_id"], unique=False)
    op.create_index("ix_graph_runs_thread_id", "graph_runs", ["thread_id"], unique=False)

    op.create_table(
        "node_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_name", sa.String(length=128), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("duration_ms", sa.Integer(), nullable=True),
        sa.Column("input_state_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("output_state_summary", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.ForeignKeyConstraint(["graph_run_id"], ["graph_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["rfp_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_node_runs_graph_run_id", "node_runs", ["graph_run_id"], unique=False)
    op.create_index("ix_node_runs_session_id", "node_runs", ["session_id"], unique=False)

    op.create_table(
        "tool_runs",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("tool_name", sa.String(length=128), nullable=False),
        sa.Column("tool_type", sa.String(length=64), nullable=False),
        sa.Column("query_text", sa.Text(), nullable=True),
        sa.Column("arguments", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("result_count", sa.Integer(), nullable=False),
        sa.Column("result_ids", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.ForeignKeyConstraint(["graph_run_id"], ["graph_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["node_run_id"], ["node_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["rfp_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_runs_graph_run_id", "tool_runs", ["graph_run_id"], unique=False)
    op.create_index("ix_tool_runs_node_run_id", "tool_runs", ["node_run_id"], unique=False)
    op.create_index("ix_tool_runs_session_id", "tool_runs", ["session_id"], unique=False)

    op.create_table(
        "llm_calls",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("draft_id", sa.String(length=128), nullable=True),
        sa.Column("graph_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("node_run_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("provider", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=128), nullable=False),
        sa.Column("call_type", sa.String(length=64), nullable=False),
        sa.Column("purpose", sa.String(length=128), nullable=False),
        sa.Column("request_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("response_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("input_tokens", sa.Integer(), nullable=False),
        sa.Column("output_tokens", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("normalized_input_tokens", sa.Integer(), nullable=False),
        sa.Column("normalized_output_tokens", sa.Integer(), nullable=False),
        sa.Column("raw_usage_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["graph_run_id"], ["graph_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["node_run_id"], ["node_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["session_id"], ["rfp_sessions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_llm_calls_graph_run_id", "llm_calls", ["graph_run_id"], unique=False)
    op.create_index("ix_llm_calls_node_run_id", "llm_calls", ["node_run_id"], unique=False)
    op.create_index("ix_llm_calls_session_id", "llm_calls", ["session_id"], unique=False)

    op.create_table(
        "session_metrics",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("latest_draft_id", sa.String(length=128), nullable=True),
        sa.Column("approved_draft_id", sa.String(length=128), nullable=True),
        sa.Column("question_type", sa.String(length=64), nullable=True),
        sa.Column("num_retrieved_chunks", sa.Integer(), nullable=False),
        sa.Column("num_cited_chunks", sa.Integer(), nullable=False),
        sa.Column("num_uncited_chunks", sa.Integer(), nullable=False),
        sa.Column("num_revision_rounds", sa.Integer(), nullable=False),
        sa.Column("approved", sa.Boolean(), nullable=False),
        sa.Column("time_to_first_draft_ms", sa.Integer(), nullable=True),
        sa.Column("time_to_approval_ms", sa.Integer(), nullable=True),
        sa.Column("total_llm_calls", sa.Integer(), nullable=False),
        sa.Column("total_tokens", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_usd", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["session_id"], ["rfp_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("session_id", name="uq_session_metrics_session_id"),
    )
    op.create_index("ix_session_metrics_session_id", "session_metrics", ["session_id"], unique=False)

    op.create_table(
        "eval_results",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("eval_run_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("session_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("metric_name", sa.String(length=128), nullable=False),
        sa.Column("score", sa.Float(), nullable=False),
        sa.Column("passed", sa.Boolean(), nullable=False),
        sa.Column("details", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["eval_run_id"], ["eval_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_id"], ["rfp_sessions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_eval_results_eval_run_id", "eval_results", ["eval_run_id"], unique=False)
    op.create_index("ix_eval_results_session_id", "eval_results", ["session_id"], unique=False)

    op.execute(
        """
        CREATE INDEX idx_document_chunks_embedding
        ON document_chunks
        USING ivfflat (embedding vector_cosine_ops)
        WITH (lists = 100)
        """
    )
    op.execute(
        """
        CREATE INDEX idx_document_chunks_fts
        ON document_chunks
        USING GIN (to_tsvector('english', chunk_text))
        """
    )
    op.create_index("idx_llm_calls_session_created", "llm_calls", ["session_id", "created_at"], unique=False)
    op.create_index("idx_llm_calls_graph_created", "llm_calls", ["graph_run_id", "created_at"], unique=False)
    op.create_index("idx_tool_runs_session_created", "tool_runs", ["session_id", "created_at"], unique=False)
    op.create_index("idx_node_runs_session_started", "node_runs", ["session_id", "started_at"], unique=False)
    op.create_index("idx_eval_results_eval_run", "eval_results", ["eval_run_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("idx_eval_results_eval_run", table_name="eval_results")
    op.drop_index("idx_node_runs_session_started", table_name="node_runs")
    op.drop_index("idx_tool_runs_session_created", table_name="tool_runs")
    op.drop_index("idx_llm_calls_graph_created", table_name="llm_calls")
    op.drop_index("idx_llm_calls_session_created", table_name="llm_calls")
    op.drop_index("idx_document_chunks_fts", table_name="document_chunks")
    op.drop_index("idx_document_chunks_embedding", table_name="document_chunks")

    op.drop_index("ix_eval_results_session_id", table_name="eval_results")
    op.drop_index("ix_eval_results_eval_run_id", table_name="eval_results")
    op.drop_table("eval_results")

    op.drop_index("ix_session_metrics_session_id", table_name="session_metrics")
    op.drop_table("session_metrics")

    op.drop_index("ix_llm_calls_session_id", table_name="llm_calls")
    op.drop_index("ix_llm_calls_node_run_id", table_name="llm_calls")
    op.drop_index("ix_llm_calls_graph_run_id", table_name="llm_calls")
    op.drop_table("llm_calls")

    op.drop_index("ix_tool_runs_session_id", table_name="tool_runs")
    op.drop_index("ix_tool_runs_node_run_id", table_name="tool_runs")
    op.drop_index("ix_tool_runs_graph_run_id", table_name="tool_runs")
    op.drop_table("tool_runs")

    op.drop_index("ix_node_runs_session_id", table_name="node_runs")
    op.drop_index("ix_node_runs_graph_run_id", table_name="node_runs")
    op.drop_table("node_runs")

    op.drop_index("ix_graph_runs_thread_id", table_name="graph_runs")
    op.drop_index("ix_graph_runs_session_id", table_name="graph_runs")
    op.drop_table("graph_runs")

    op.drop_index("ix_rfp_reviews_session_id", table_name="rfp_reviews")
    op.drop_table("rfp_reviews")

    op.drop_index("ix_document_chunks_document_id", table_name="document_chunks")
    op.drop_table("document_chunks")

    op.drop_table("eval_runs")

    op.drop_index("ix_rfp_sessions_graph_thread_id", table_name="rfp_sessions")
    op.drop_table("rfp_sessions")

    op.drop_table("documents")
