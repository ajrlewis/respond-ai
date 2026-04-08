"""add response document tables

Revision ID: 9f2c0a1f4d18
Revises: 146703db33e7
Create Date: 2026-04-08 01:15:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = "9f2c0a1f4d18"
down_revision: Union[str, Sequence[str], None] = "146703db33e7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Upgrade schema."""

    op.create_table(
        "response_documents",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("source_filename", sa.String(length=255), nullable=True),
        sa.Column("source_text", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )

    op.create_table(
        "response_questions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("extracted_text", sa.Text(), nullable=False),
        sa.Column("normalized_title", sa.String(length=255), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["response_document_id"], ["response_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_response_questions_response_document_id", "response_questions", ["response_document_id"], unique=False)

    op.create_table(
        "response_document_versions",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("response_document_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("label", sa.String(length=128), nullable=False),
        sa.Column("created_by", sa.String(length=128), nullable=True),
        sa.Column("parent_version_id", postgresql.UUID(as_uuid=True), nullable=True),
        sa.Column("is_final", sa.Boolean(), nullable=False),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["parent_version_id"], ["response_document_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["response_document_id"], ["response_documents.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("response_document_id", "version_number", name="uq_response_doc_version_number"),
    )
    op.create_index("ix_response_document_versions_response_document_id", "response_document_versions", ["response_document_id"], unique=False)

    op.create_table(
        "response_document_sections",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("draft_version_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("question_id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("content_markdown", sa.Text(), nullable=False),
        sa.Column("evidence_refs_payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("confidence_score", sa.Float(), nullable=True),
        sa.Column("coverage_score", sa.Float(), nullable=True),
        sa.Column("metadata", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.ForeignKeyConstraint(["draft_version_id"], ["response_document_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["question_id"], ["response_questions.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("draft_version_id", "question_id", name="uq_response_doc_section_question"),
    )
    op.create_index("ix_response_document_sections_draft_version_id", "response_document_sections", ["draft_version_id"], unique=False)
    op.create_index("ix_response_document_sections_question_id", "response_document_sections", ["question_id"], unique=False)


def downgrade() -> None:
    """Downgrade schema."""

    op.drop_index("ix_response_document_sections_question_id", table_name="response_document_sections")
    op.drop_index("ix_response_document_sections_draft_version_id", table_name="response_document_sections")
    op.drop_table("response_document_sections")

    op.drop_index("ix_response_document_versions_response_document_id", table_name="response_document_versions")
    op.drop_table("response_document_versions")

    op.drop_index("ix_response_questions_response_document_id", table_name="response_questions")
    op.drop_table("response_questions")

    op.drop_table("response_documents")
