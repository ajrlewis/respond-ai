"""Structured schemas for optional LLM-judge evals."""

from __future__ import annotations

from pydantic import BaseModel, Field


class LLMJudgeEvalResult(BaseModel):
    """LLM-judge evaluation payload for one approved session."""

    score: float = Field(ge=0.0, le=1.0, description="Overall quality score from 0-1.")
    passed: bool = Field(description="Whether the answer passes quality threshold.")
    rationale: str = Field(default="", description="Short explanation for the score.")
    strengths: list[str] = Field(default_factory=list, description="Positive traits in the answer.")
    risks: list[str] = Field(default_factory=list, description="Observed issues or concerns.")
