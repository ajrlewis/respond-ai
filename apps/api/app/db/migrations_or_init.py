"""Database bootstrap helpers."""

import logging

from sqlalchemy import text

from app.core.database import async_engine, engine
from app.db.models import Base

logger = logging.getLogger(__name__)


def init_database() -> None:
    """Create required extensions and tables for local/demo use."""

    logger.info("Initializing database schema (sync)")
    with engine.begin() as connection:
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        Base.metadata.create_all(bind=connection)
        connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS current_node VARCHAR(64)"))
        connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS confidence_payload JSONB DEFAULT '{}'::jsonb")
        )
        connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS answer_versions_payload JSONB DEFAULT '[]'::jsonb")
        )
        connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS final_version_number INTEGER"))
        connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS reviewer_action VARCHAR(32)"))
        connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS reviewer_id VARCHAR(128)"))
        connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS evidence_gaps_acknowledged BOOLEAN DEFAULT FALSE")
        )
        connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS evidence_gaps_acknowledged_at TIMESTAMPTZ"))
        connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS final_audit_payload JSONB DEFAULT '{}'::jsonb")
        )
        connection.execute(
            text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS excluded_evidence_keys JSONB DEFAULT '[]'::jsonb")
        )
        connection.execute(
            text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS reviewed_evidence_gaps BOOLEAN DEFAULT FALSE")
        )
        connection.execute(text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS evidence_gaps_acknowledged_at TIMESTAMPTZ"))
        connection.execute(text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS reviewer_id VARCHAR(128)"))
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
                ON document_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        )
        connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_fts
                ON document_chunks
                USING GIN (to_tsvector('english', chunk_text))
                """
            )
        )
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_llm_calls_session_created ON llm_calls (session_id, created_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_llm_calls_graph_created ON llm_calls (graph_run_id, created_at)"))
        connection.execute(text("ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS normalized_input_tokens INTEGER DEFAULT 0"))
        connection.execute(text("ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS normalized_output_tokens INTEGER DEFAULT 0"))
        connection.execute(text("ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS raw_usage_payload JSONB DEFAULT '{}'::jsonb"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_tool_runs_session_created ON tool_runs (session_id, created_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_node_runs_session_started ON node_runs (session_id, started_at)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS idx_eval_results_eval_run ON eval_results (eval_run_id)"))
    logger.info("Database schema initialization complete (sync)")


async def init_database_async() -> None:
    """Create required extensions and tables for async API startup."""

    logger.info("Initializing database schema (async)")
    async with async_engine.begin() as connection:
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await connection.execute(text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
        await connection.run_sync(Base.metadata.create_all)
        await connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS current_node VARCHAR(64)"))
        await connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS confidence_payload JSONB DEFAULT '{}'::jsonb")
        )
        await connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS answer_versions_payload JSONB DEFAULT '[]'::jsonb")
        )
        await connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS final_version_number INTEGER"))
        await connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ"))
        await connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS reviewer_action VARCHAR(32)"))
        await connection.execute(text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS reviewer_id VARCHAR(128)"))
        await connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS evidence_gaps_acknowledged BOOLEAN DEFAULT FALSE")
        )
        await connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS evidence_gaps_acknowledged_at TIMESTAMPTZ")
        )
        await connection.execute(
            text("ALTER TABLE rfp_sessions ADD COLUMN IF NOT EXISTS final_audit_payload JSONB DEFAULT '{}'::jsonb")
        )
        await connection.execute(
            text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS excluded_evidence_keys JSONB DEFAULT '[]'::jsonb")
        )
        await connection.execute(
            text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS reviewed_evidence_gaps BOOLEAN DEFAULT FALSE")
        )
        await connection.execute(text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS evidence_gaps_acknowledged_at TIMESTAMPTZ"))
        await connection.execute(text("ALTER TABLE rfp_reviews ADD COLUMN IF NOT EXISTS reviewer_id VARCHAR(128)"))
        await connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_embedding
                ON document_chunks
                USING ivfflat (embedding vector_cosine_ops)
                WITH (lists = 100)
                """
            )
        )
        await connection.execute(
            text(
                """
                CREATE INDEX IF NOT EXISTS idx_document_chunks_fts
                ON document_chunks
                USING GIN (to_tsvector('english', chunk_text))
                """
            )
        )
        await connection.execute(text("CREATE INDEX IF NOT EXISTS idx_llm_calls_session_created ON llm_calls (session_id, created_at)"))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS idx_llm_calls_graph_created ON llm_calls (graph_run_id, created_at)"))
        await connection.execute(text("ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS normalized_input_tokens INTEGER DEFAULT 0"))
        await connection.execute(text("ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS normalized_output_tokens INTEGER DEFAULT 0"))
        await connection.execute(text("ALTER TABLE llm_calls ADD COLUMN IF NOT EXISTS raw_usage_payload JSONB DEFAULT '{}'::jsonb"))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS idx_tool_runs_session_created ON tool_runs (session_id, created_at)"))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS idx_node_runs_session_started ON node_runs (session_id, started_at)"))
        await connection.execute(text("CREATE INDEX IF NOT EXISTS idx_eval_results_eval_run ON eval_results (eval_run_id)"))
    logger.info("Database schema initialization complete (async)")
