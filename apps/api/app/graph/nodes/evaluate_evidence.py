"""Evidence evaluation and legacy cross-reference node implementations."""

from __future__ import annotations

import logging
import uuid

from app.ai.schemas import RetrievalPlanResult
from app.core.config import settings
from app.db.models import RFPSession
from app.graph.nodes._execution import execute_node
from app.graph.state import WorkflowState
from app.services.confidence import build_structured_confidence_payload, render_confidence_notes
from app.services.evidence_analysis import (
    augment_plan_for_retry,
    build_confidence_notes,
    cross_reference_with_model,
    curate_evidence,
    evaluate_evidence_with_model,
    evidence_item_key,
    normalize_evaluation_result,
    partition_evidence,
)
from app.services.planning import retrieval_plan_fallback

logger = logging.getLogger(__name__)


async def evaluate_evidence_node(nodes, state: WorkflowState) -> WorkflowState:
    """Evaluate evidence sufficiency and select draft-ready chunks."""

    async def _operation() -> WorkflowState:
        question = state.get("question_text", "")
        retry_count = int(state.get("retry_count", 0) or 0)
        plan = RetrievalPlanResult.model_validate(state.get("retrieval_plan") or retrieval_plan_fallback(question).model_dump())
        candidates = list(state.get("retrieved_evidence", []) or state.get("retrieved_chunks", []) or [])
        logger.debug(
            "Node evaluate_evidence started session_id=%s candidate_count=%d retry=%d",
            state.get("session_id"),
            len(candidates),
            retry_count,
        )

        evaluation = await evaluate_evidence_with_model(
            question=question,
            plan=plan,
            evidence=candidates,
        )
        evaluation = normalize_evaluation_result(evaluation=evaluation, evidence=candidates, plan=plan)
        selected, rejected, annotated = partition_evidence(
            evidence=candidates,
            selected_ids=evaluation.selected_chunk_ids,
            rejected_ids=evaluation.rejected_chunk_ids,
        )

        retrieval_strategy = str(state.get("retrieval_strategy_used", "")).strip() or plan.retrieval_strategy
        retrieval_notes = build_confidence_notes(selected or candidates)
        if evaluation.evidence_summary.strip():
            retrieval_notes = f"{retrieval_notes} {evaluation.evidence_summary.strip()}".strip()

        effective_retry_count = retry_count
        final_evaluation = evaluation
        if evaluation.recommended_action == "retrieve_more" and retry_count >= 1:
            final_evaluation = evaluation.model_copy(
                update={
                    "recommended_action": "proceed_with_caveats",
                    "notes_for_drafting": [
                        *evaluation.notes_for_drafting,
                        "Additional retrieval was already attempted once; proceed with explicit caveats.",
                    ],
                }
            )

        confidence_payload = build_structured_confidence_payload(
            evaluation=final_evaluation,
            retrieval_strategy_used=retrieval_strategy,
            retrieval_notes=retrieval_notes,
            fallback_score=0.35 if final_evaluation.coverage == "weak" else 0.55,
            fallback_compliance="unknown",
            fallback_notes="Evidence evaluation completed without draft metadata extraction.",
            fallback_gaps=final_evaluation.missing_information,
        )
        confidence_notes = render_confidence_notes(confidence_payload)

        next_plan = plan
        if final_evaluation.recommended_action == "retrieve_more" and retry_count < 1:
            effective_retry_count = retry_count + 1
            next_plan = augment_plan_for_retry(plan=plan, evaluation=final_evaluation)

        logger.info(
            "Node evaluate_evidence completed session_id=%s coverage=%s selected=%d rejected=%d action=%s retry=%d",
            state.get("session_id"),
            final_evaluation.coverage,
            len(selected),
            len(rejected),
            final_evaluation.recommended_action,
            effective_retry_count,
        )

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                session.evidence_payload = annotated
                session.selected_evidence_payload = selected
                session.rejected_evidence_payload = rejected
                session.evidence_evaluation_payload = final_evaluation.model_dump()
                session.retrieval_plan_payload = next_plan.model_dump()
                session.retrieval_strategy_used = retrieval_strategy
                session.retry_count = effective_retry_count
                session.confidence_notes = confidence_notes
                session.confidence_payload = confidence_payload
                await db.commit()

        return {
            "retrieval_plan": next_plan.model_dump(),
            "retrieval_strategy_used": retrieval_strategy,
            "retry_count": effective_retry_count,
            "selected_evidence": selected,
            "rejected_evidence": rejected,
            "curated_evidence": selected,
            "evidence_evaluation": final_evaluation.model_dump(),
            "confidence_notes": confidence_notes,
            "confidence_payload": confidence_payload,
            "current_node": "evaluate_evidence",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="evaluate_evidence",
        state=state,
        operation=_operation,
    )


async def cross_reference_evidence_node(nodes, state: WorkflowState) -> WorkflowState:
    """Legacy evidence cross-reference node retained for compatibility."""

    async def _operation() -> WorkflowState:
        candidates = state.get("retrieved_evidence", [])
        logger.debug(
            "Node cross_reference_evidence started session_id=%s candidate_count=%d",
            state.get("session_id"),
            len(candidates),
        )
        if not candidates:
            logger.warning("No evidence candidates found session_id=%s", state.get("session_id"))
            confidence_payload = build_structured_confidence_payload(
                fallback_score=0.0,
                fallback_compliance="unknown",
                fallback_notes="No relevant internal evidence was retrieved.",
                fallback_gaps=["No relevant internal evidence was retrieved."],
            )
            return {
                "curated_evidence": [],
                "evidence_synthesis": {},
                "confidence_notes": render_confidence_notes(confidence_payload),
                "confidence_payload": confidence_payload,
                "current_node": "cross_reference_evidence",
                "session_id": state.get("session_id"),
            }

        ranked = curate_evidence(candidates, final_k=settings.final_evidence_k)
        synthesis = await cross_reference_with_model(
            question=state.get("question_text", ""),
            question_type=state.get("question_type", "other"),
            evidence=ranked,
        )
        if synthesis and synthesis.selected_chunk_ids:
            selected_ids = {item.strip() for item in synthesis.selected_chunk_ids if item.strip()}
            filtered_ranked = [
                item
                for item in ranked
                if str(item.get("chunk_id", "")).strip() in selected_ids
                or evidence_item_key(item) in selected_ids
            ]
            if filtered_ranked:
                ranked = filtered_ranked

        confidence_notes = build_confidence_notes(ranked)
        retrieval_notes = confidence_notes
        if synthesis and synthesis.evidence_summary.strip():
            retrieval_notes = f"{confidence_notes} {synthesis.evidence_summary.strip()}".strip()

        confidence_payload = build_structured_confidence_payload(
            synthesis=synthesis,
            fallback_score=None,
            fallback_compliance="unknown",
            fallback_notes="; ".join(synthesis.contradictions_found) if synthesis else "",
            fallback_gaps=synthesis.missing_information if synthesis else [],
            retrieval_notes=retrieval_notes,
        )
        logger.info(
            "Node cross_reference_evidence completed session_id=%s curated_count=%d",
            state.get("session_id"),
            len(ranked),
        )

        async with nodes._db() as db:
            session = await db.get(RFPSession, uuid.UUID(state["session_id"]))
            if session:
                session.evidence_payload = ranked
                session.confidence_notes = retrieval_notes
                session.confidence_payload = confidence_payload
                await db.commit()

        return {
            "curated_evidence": ranked,
            "evidence_synthesis": synthesis.model_dump() if synthesis else {},
            "confidence_notes": retrieval_notes,
            "confidence_payload": confidence_payload,
            "current_node": "cross_reference_evidence",
            "session_id": state.get("session_id"),
        }

    return await execute_node(
        nodes=nodes,
        node_name="cross_reference_evidence",
        state=state,
        operation=_operation,
    )
