"""Evaluation routes for observability reporting."""

from __future__ import annotations

import logging
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import require_current_user
from app.core.database import get_db
from app.db.models import EvalRun
from app.evals.report import summarize_eval_run
from app.evals.runner import EvalRunner
from app.schemas.evals import EvalRunListItemOut, EvalRunSummaryOut, EvalRunTriggerRequest

router = APIRouter(prefix="/api/evals", tags=["evals"], dependencies=[Depends(require_current_user)])
logger = logging.getLogger(__name__)


@router.post("/run", response_model=EvalRunSummaryOut)
async def run_evals(payload: EvalRunTriggerRequest, db: AsyncSession = Depends(get_db)) -> EvalRunSummaryOut:
    """Run offline evaluations over persisted sessions and return run summary."""

    logger.info("Eval run requested limit=%d explicit_sessions=%d", payload.limit, len(payload.session_ids))
    runner = EvalRunner()
    summary = await runner.run(limit=payload.limit, session_ids=payload.session_ids)

    report = await summarize_eval_run(db, summary.eval_run_id)
    if not report:
        raise HTTPException(status_code=500, detail="Eval run completed but summary could not be loaded.")
    return EvalRunSummaryOut.model_validate(report)


@router.get("/runs", response_model=list[EvalRunListItemOut])
async def list_eval_runs(
    limit: int = Query(default=20, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
) -> list[EvalRunListItemOut]:
    """List recent eval runs."""

    rows = list(
        (
            await db.execute(
                select(EvalRun)
                .order_by(EvalRun.started_at.desc())
                .limit(limit)
            )
        )
        .scalars()
        .all()
    )
    return [
        EvalRunListItemOut(
            id=str(row.id),
            status=row.status,
            target_session_count=row.target_session_count,
            evaluated_session_count=row.evaluated_session_count,
            average_score=row.average_score,
            started_at=row.started_at,
            completed_at=row.completed_at,
        )
        for row in rows
    ]


@router.get("/runs/{run_id}", response_model=EvalRunSummaryOut)
async def get_eval_run(run_id: UUID, db: AsyncSession = Depends(get_db)) -> EvalRunSummaryOut:
    """Return detailed summary for one eval run."""

    report = await summarize_eval_run(db, str(run_id))
    if not report:
        raise HTTPException(status_code=404, detail="Eval run not found")
    return EvalRunSummaryOut.model_validate(report)
