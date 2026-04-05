"""Structured drafting/revision metadata schemas."""

from __future__ import annotations

from pydantic import BaseModel, Field


class DraftMetadataResult(BaseModel):
    """Structured metadata extracted from a draft answer."""

    citations_used: list[str] = Field(
        default_factory=list,
        description="Citation ids referenced by the answer text.",
    )
    coverage_notes: str = Field(
        default="",
        description="Coverage quality notes for reviewer context.",
    )
    confidence_notes: str = Field(
        default="",
        description="Model confidence rationale and caveats.",
    )
    missing_info_notes: list[str] = Field(
        default_factory=list,
        description="Missing information needed for stronger grounding.",
    )
    compliance_flags: list[str] = Field(
        default_factory=list,
        description="Potential policy/compliance concerns to review.",
    )


class RevisionIntentResult(BaseModel):
    """Structured intent extracted from reviewer feedback."""

    reviewer_request_summary: str = Field(
        default="",
        description="Normalized summary of the reviewer request.",
    )
    changes_requested: list[str] = Field(
        default_factory=list,
        description="Specific requested edits.",
    )
    expected_improvements: list[str] = Field(
        default_factory=list,
        description="Expected output quality improvements after revision.",
    )
