"""Agent-internal schema contracts."""

from pydantic import BaseModel, Field


class ClassificationResult(BaseModel):
    """Question classification output."""

    category: str = Field(description="One of the supported question categories.")
    rationale: str = Field(description="Short explanation for auditability.")


class DraftResult(BaseModel):
    """Drafting output with confidence caveats."""

    answer: str
    confidence_notes: str
