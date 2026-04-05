"""Reporting helpers for persisted evaluation runs."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EvalResult, EvalRun


@dataclass(slots=True)
class MetricAggregate:
    """Aggregate stats for one metric across sessions in a run."""

    metric_name: str
    count: int
    avg_score: float
    pass_rate: float


async def summarize_eval_run(db: AsyncSession, eval_run_id: str) -> dict | None:
    """Return aggregate and per-session score summary for an eval run id."""

    try:
        parsed_id = uuid.UUID(str(eval_run_id))
    except ValueError:
        return None

    run = await db.get(EvalRun, parsed_id)
    if not run:
        return None

    results = list(
        (
            await db.execute(
                select(EvalResult)
                .where(EvalResult.eval_run_id == run.id)
                .order_by(EvalResult.created_at.asc())
            )
        )
        .scalars()
        .all()
    )

    metric_scores: dict[str, list[tuple[float, bool]]] = defaultdict(list)
    per_session_overall: list[dict] = []

    for row in results:
        metric_scores[row.metric_name].append((float(row.score), bool(row.passed)))
        if row.metric_name == "overall":
            per_session_overall.append(
                {
                    "session_id": str(row.session_id),
                    "score": float(row.score),
                    "passed": bool(row.passed),
                    "details": row.details or {},
                }
            )

    aggregates: list[MetricAggregate] = []
    for metric_name, rows in metric_scores.items():
        count = len(rows)
        avg = sum(score for score, _ in rows) / count if count else 0.0
        pass_rate = sum(1 for _, passed in rows if passed) / count if count else 0.0
        aggregates.append(
            MetricAggregate(
                metric_name=metric_name,
                count=count,
                avg_score=round(avg, 4),
                pass_rate=round(pass_rate, 4),
            )
        )

    aggregates.sort(key=lambda item: item.metric_name)
    per_session_overall.sort(key=lambda row: row["score"], reverse=True)

    return {
        "id": str(run.id),
        "status": run.status,
        "target_session_count": run.target_session_count,
        "evaluated_session_count": run.evaluated_session_count,
        "average_score": run.average_score,
        "started_at": run.started_at,
        "completed_at": run.completed_at,
        "metadata": run.metadata_json or {},
        "error_message": run.error_message,
        "metric_aggregates": [
            {
                "metric_name": item.metric_name,
                "count": item.count,
                "avg_score": item.avg_score,
                "pass_rate": item.pass_rate,
            }
            for item in aggregates
        ],
        "session_overall_scores": per_session_overall,
    }
