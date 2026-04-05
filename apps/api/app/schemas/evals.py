"""Evaluation API schemas."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class EvalRunTriggerRequest(BaseModel):
    """Run-evals endpoint request."""

    limit: int = Field(default=50, ge=1, le=500)
    session_ids: list[str] = Field(default_factory=list)


class EvalMetricAggregateOut(BaseModel):
    """Metric aggregate row for one eval run."""

    metric_name: str
    count: int
    avg_score: float
    pass_rate: float


class EvalSessionScoreOut(BaseModel):
    """Overall per-session score row for one eval run."""

    session_id: str
    score: float
    passed: bool
    details: dict = Field(default_factory=dict)


class EvalRunSummaryOut(BaseModel):
    """Expanded eval run summary payload."""

    id: str
    status: str
    target_session_count: int
    evaluated_session_count: int
    average_score: float | None = None
    started_at: datetime
    completed_at: datetime | None = None
    metadata: dict = Field(default_factory=dict)
    error_message: str | None = None
    metric_aggregates: list[EvalMetricAggregateOut] = Field(default_factory=list)
    session_overall_scores: list[EvalSessionScoreOut] = Field(default_factory=list)


class EvalRunListItemOut(BaseModel):
    """Compact eval run list row."""

    id: str
    status: str
    target_session_count: int
    evaluated_session_count: int
    average_score: float | None = None
    started_at: datetime
    completed_at: datetime | None = None
