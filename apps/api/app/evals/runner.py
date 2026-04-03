"""Evaluation runner that scores historical sessions from persisted observability data."""

from __future__ import annotations

from dataclasses import dataclass
import logging
import uuid

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.ai import AIConfigurationError, AIProviderError, get_structured_model
from app.ai.schemas import LLMJudgeEvalResult
from app.core.config import settings
from app.core.database import AsyncSessionLocal
from app.db.models import EvalResult, EvalRun, LLMCall, RFPReview, RFPSession, SessionMetric
from app.evals.evaluators import SessionEvalInput, SessionEvalScore, evaluate_session
from app.prompts import load_system_prompt, render_user_prompt

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class EvalRunSummary:
    """Returned summary of one eval execution."""

    eval_run_id: str
    target_session_count: int
    evaluated_session_count: int
    average_score: float | None
    session_scores: list[SessionEvalScore]


class EvalRunner:
    """Runs lightweight offline evaluations against persisted session artefacts."""

    def __init__(self, session_factory: async_sessionmaker[AsyncSession] = AsyncSessionLocal) -> None:
        self.session_factory = session_factory

    async def run(
        self,
        *,
        limit: int = 50,
        session_ids: list[str] | None = None,
        metadata: dict | None = None,
    ) -> EvalRunSummary:
        """Execute evals and persist metric-level results."""

        normalized_ids: list[uuid.UUID] = []
        for session_id in session_ids or []:
            try:
                normalized_ids.append(uuid.UUID(str(session_id)))
            except ValueError:
                logger.warning("Skipping invalid session_id=%s", session_id)

        async with self.session_factory() as db:
            eval_run = EvalRun(
                status="running",
                target_session_count=0,
                metadata_json=metadata or {},
            )
            db.add(eval_run)
            await db.commit()
            await db.refresh(eval_run)

            try:
                sessions = await self._fetch_sessions(db, limit=limit, session_ids=normalized_ids)
                eval_run.target_session_count = len(sessions)
                await db.commit()

                session_scores: list[SessionEvalScore] = []
                for session in sessions:
                    score = await self._evaluate_single_session(db, eval_run_id=eval_run.id, session=session)
                    session_scores.append(score)

                average_score = (
                    round(sum(item.overall_score for item in session_scores) / len(session_scores), 4)
                    if session_scores
                    else None
                )
                eval_run.status = "completed"
                eval_run.evaluated_session_count = len(session_scores)
                eval_run.average_score = average_score
                await db.commit()

                return EvalRunSummary(
                    eval_run_id=str(eval_run.id),
                    target_session_count=len(sessions),
                    evaluated_session_count=len(session_scores),
                    average_score=average_score,
                    session_scores=session_scores,
                )
            except Exception as exc:
                eval_run.status = "error"
                eval_run.error_message = str(exc)
                await db.commit()
                raise

    async def _fetch_sessions(
        self,
        db: AsyncSession,
        *,
        limit: int,
        session_ids: list[uuid.UUID],
    ) -> list[RFPSession]:
        stmt = select(RFPSession).order_by(RFPSession.created_at.desc())
        if session_ids:
            stmt = stmt.where(RFPSession.id.in_(session_ids))
        else:
            stmt = stmt.limit(max(1, min(limit, 500)))
        return list((await db.execute(stmt)).scalars().all())

    async def _evaluate_single_session(
        self,
        db: AsyncSession,
        *,
        eval_run_id: uuid.UUID,
        session: RFPSession,
    ) -> SessionEvalScore:
        metrics_row = (
            await db.execute(select(SessionMetric).where(SessionMetric.session_id == session.id))
        ).scalar_one_or_none()

        total_reviews = int(
            (
                await db.execute(
                    select(func.count(RFPReview.id)).where(RFPReview.session_id == session.id)
                )
            ).scalar_one()
            or 0
        )
        revision_rounds = int(
            (
                await db.execute(
                    select(func.count(RFPReview.id)).where(
                        RFPReview.session_id == session.id,
                        RFPReview.reviewer_action == "revise",
                    )
                )
            ).scalar_one()
            or 0
        )

        llm_agg = (
            await db.execute(
                select(
                    func.coalesce(func.sum(LLMCall.total_tokens), 0),
                    func.coalesce(func.sum(LLMCall.estimated_cost_usd), 0.0),
                ).where(LLMCall.session_id == session.id)
            )
        ).one()

        num_retrieved_chunks = (
            metrics_row.num_retrieved_chunks
            if metrics_row is not None
            else len(list(getattr(session, "evidence_payload", []) or []))
        )

        num_cited_chunks = metrics_row.num_cited_chunks if metrics_row is not None else self._derive_cited_count(session)
        total_tokens = metrics_row.total_tokens if metrics_row is not None else int(llm_agg[0] or 0)
        estimated_cost = metrics_row.estimated_cost_usd if metrics_row is not None else float(llm_agg[1] or 0.0)
        retrieval_plan = getattr(session, "retrieval_plan_payload", {}) or {}
        evidence_evaluation = getattr(session, "evidence_evaluation_payload", {}) or {}
        confidence_payload = getattr(session, "confidence_payload", {}) or {}

        sub_questions = retrieval_plan.get("sub_questions", []) if isinstance(retrieval_plan, dict) else []
        missing_information = (
            evidence_evaluation.get("missing_information", [])
            if isinstance(evidence_evaluation, dict)
            else []
        )

        input_record = SessionEvalInput(
            session_id=str(session.id),
            approved=bool(metrics_row.approved if metrics_row is not None else getattr(session, "status", "") == "approved"),
            has_final_answer=bool((getattr(session, "final_answer", None) or "").strip()),
            num_retrieved_chunks=int(num_retrieved_chunks or 0),
            num_cited_chunks=int(num_cited_chunks or 0),
            num_revision_rounds=int(metrics_row.num_revision_rounds if metrics_row is not None else revision_rounds),
            review_event_count=int(total_reviews),
            time_to_first_draft_ms=metrics_row.time_to_first_draft_ms if metrics_row is not None else None,
            time_to_approval_ms=metrics_row.time_to_approval_ms if metrics_row is not None else None,
            total_tokens=int(total_tokens or 0),
            estimated_cost_usd=(float(estimated_cost) if estimated_cost is not None else None),
            has_retrieval_plan=isinstance(retrieval_plan, dict) and bool(retrieval_plan),
            planner_sub_question_count=len([item for item in sub_questions if isinstance(item, str) and item.strip()]),
            retrieval_strategy_used=(
                str(getattr(session, "retrieval_strategy_used", "")).strip()
                or str(confidence_payload.get("retrieval_strategy", "")).strip()
                or None
            ),
            evidence_coverage=(
                str(evidence_evaluation.get("coverage", "")).strip()
                if isinstance(evidence_evaluation, dict)
                else None
            ),
            recommended_action=(
                str(evidence_evaluation.get("recommended_action", "")).strip()
                if isinstance(evidence_evaluation, dict)
                else None
            ),
            missing_information_count=len(
                [item for item in missing_information if isinstance(item, str) and item.strip()]
            ),
            retrieval_retry_count=int(getattr(session, "retry_count", 0) or 0),
        )

        score = evaluate_session(input_record)

        llm_judge: LLMJudgeEvalResult | None = None
        if settings.enable_llm_judge_evals and bool((getattr(session, "final_answer", "") or "").strip()):
            llm_judge = await self._run_llm_judge(
                session=session,
                record=input_record,
            )

        for metric in score.metrics:
            db.add(
                EvalResult(
                    eval_run_id=eval_run_id,
                    session_id=session.id,
                    metric_name=metric.name,
                    score=metric.score,
                    passed=metric.passed,
                    details=metric.details,
                )
            )

        db.add(
            EvalResult(
                eval_run_id=eval_run_id,
                session_id=session.id,
                metric_name="overall",
                score=score.overall_score,
                passed=score.passed,
                details={
                    "metric_count": len(score.metrics),
                    "passed_metrics": [metric.name for metric in score.metrics if metric.passed],
                },
            )
        )

        if llm_judge is not None:
            db.add(
                EvalResult(
                    eval_run_id=eval_run_id,
                    session_id=session.id,
                    metric_name="llm_judge",
                    score=llm_judge.score,
                    passed=llm_judge.passed,
                    details={
                        "rationale": llm_judge.rationale,
                        "strengths": llm_judge.strengths,
                        "risks": llm_judge.risks,
                    },
                )
            )

        await db.commit()
        return score

    async def _run_llm_judge(
        self,
        *,
        session: RFPSession,
        record: SessionEvalInput,
    ) -> LLMJudgeEvalResult | None:
        try:
            judge = get_structured_model(schema=LLMJudgeEvalResult, purpose="evaluation")
            return await judge.ainvoke(
                system_prompt=load_system_prompt("eval_judge"),
                user_prompt=render_user_prompt(
                    "eval_judge",
                    {
                        "session_id": record.session_id,
                        "approved": record.approved,
                        "question_type": str(getattr(session, "question_type", "") or "other"),
                        "final_answer": str(getattr(session, "final_answer", "") or ""),
                        "num_retrieved_chunks": record.num_retrieved_chunks,
                        "num_cited_chunks": record.num_cited_chunks,
                        "num_revision_rounds": record.num_revision_rounds,
                        "total_tokens": record.total_tokens,
                        "estimated_cost_usd": record.estimated_cost_usd,
                    },
                ),
                temperature=0,
            )
        except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
            logger.warning("LLM judge eval skipped session_id=%s error=%s", record.session_id, exc)
            return None

    @staticmethod
    def _derive_cited_count(session: RFPSession) -> int:
        final_audit = getattr(session, "final_audit_payload", {}) or {}
        included = final_audit.get("included_chunk_ids", []) if isinstance(final_audit, dict) else []
        if isinstance(included, list) and included:
            return len({str(item).strip() for item in included if str(item).strip()})
        return 0
