"""Drafting, revision, and polish generation services."""

from __future__ import annotations

import logging
from typing import Literal

from app.ai import AIConfigurationError, AIProviderError, get_chat_model, get_structured_model
from app.ai.schemas import DraftMetadataResult, EvidenceEvaluationResult, EvidenceSynthesisResult, RetrievalPlanResult, RevisionIntentResult
from app.prompts import get_tone_guidelines, load_system_prompt, render_prompt_template, render_user_prompt
from app.services.citations import extract_answer_citations, normalize_answer_citations
from app.services.confidence import (
    build_structured_confidence_payload,
    format_evidence_blob,
    render_confidence_notes,
)

logger = logging.getLogger(__name__)


async def extract_draft_metadata(
    *,
    question: str,
    question_type: str,
    draft_answer: str,
    evidence_blob: str,
    purpose: Literal["draft_metadata", "revision_intent"] = "draft_metadata",
) -> DraftMetadataResult:
    """Extract structured drafting metadata with deterministic fallback."""

    try:
        extractor = get_structured_model(schema=DraftMetadataResult, purpose=purpose)
        return await extractor.ainvoke(
            system_prompt=load_system_prompt("draft_metadata"),
            user_prompt=render_user_prompt(
                "draft_metadata",
                {
                    "question": question,
                    "question_type": question_type,
                    "draft_answer": draft_answer,
                    "evidence": evidence_blob,
                },
            ),
            temperature=0,
        )
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.warning("Draft metadata extraction fallback applied error=%s", exc)

    compliance_flags: list[str] = []
    lowered = draft_answer.lower()
    for phrase in ["guaranteed", "guarantee", "certain returns", "no risk"]:
        if phrase in lowered:
            compliance_flags.append(f"Potential promissory language detected: '{phrase}'.")

    missing_notes = []
    if "insufficient" in lowered or "unable" in lowered:
        missing_notes.append("Answer indicates potentially missing evidence coverage.")

    return DraftMetadataResult(
        citations_used=extract_answer_citations(draft_answer),
        coverage_notes="Fallback metadata extraction was used.",
        confidence_notes="Structured metadata extraction was unavailable; reviewer should verify citations and tone.",
        missing_info_notes=missing_notes,
        compliance_flags=compliance_flags,
    )


async def extract_revision_intent(
    *,
    question: str,
    reviewer_feedback: str,
) -> RevisionIntentResult:
    """Extract structured reviewer intent with deterministic fallback."""

    feedback = reviewer_feedback.strip() or "No additional reviewer comments provided."
    try:
        extractor = get_structured_model(schema=RevisionIntentResult, purpose="revision_intent")
        return await extractor.ainvoke(
            system_prompt=load_system_prompt("revision_intent"),
            user_prompt=render_user_prompt(
                "revision_intent",
                {
                    "question": question,
                    "reviewer_feedback": feedback,
                },
            ),
            temperature=0,
        )
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.warning("Revision intent extraction fallback applied error=%s", exc)

    return RevisionIntentResult(
        reviewer_request_summary=feedback,
        changes_requested=[feedback],
        expected_improvements=["Improve alignment with reviewer feedback while preserving citations."],
    )


async def draft_answer(
    *,
    question: str,
    question_type: str,
    tone: str,
    evidence: list[dict],
    existing_confidence: str,
    synthesis: dict | None = None,
    retrieval_plan: dict | None = None,
    evidence_evaluation: dict | None = None,
    retrieval_strategy_used: str | None = None,
) -> tuple[str, str, dict, dict]:
    """Generate a grounded draft answer from selected evidence."""

    if not evidence:
        logger.warning("Draft requested without evidence; returning low-confidence response")
        evaluation_obj = (
            EvidenceEvaluationResult.model_validate(evidence_evaluation or {})
            if evidence_evaluation
            else None
        )
        confidence_payload = build_structured_confidence_payload(
            evaluation=evaluation_obj,
            retrieval_strategy_used=retrieval_strategy_used,
            fallback_score=0.0,
            fallback_compliance="unknown",
            fallback_notes="No supporting chunks were retrieved.",
            fallback_gaps=["No supporting chunks were retrieved."],
            retrieval_notes=existing_confidence,
        )
        return (
            "Insufficient internal evidence was retrieved to confidently draft a response. "
            "Please add internal material before finalizing this answer.",
            render_confidence_notes(confidence_payload),
            confidence_payload,
            {},
        )

    evidence_blob = format_evidence_blob(evidence)
    tone_guidelines = get_tone_guidelines(tone)
    synthesis_obj = EvidenceSynthesisResult.model_validate(synthesis or {}) if synthesis else None
    evaluation_obj = (
        EvidenceEvaluationResult.model_validate(evidence_evaluation or {})
        if evidence_evaluation
        else None
    )
    plan_obj = RetrievalPlanResult.model_validate(retrieval_plan or {}) if retrieval_plan else None
    retrieval_plan_summary = "No explicit retrieval plan was provided."
    if plan_obj:
        sub_q = "; ".join(plan_obj.sub_questions[:4]) or "No explicit sub-questions."
        priorities = ", ".join(plan_obj.priority_sources[:5]) or "unspecified"
        retrieval_plan_summary = (
            f"{plan_obj.reasoning_summary} "
            f"Sub-questions: {sub_q}. "
            f"Priority sources: {priorities}. "
            f"Strategy: {plan_obj.retrieval_strategy}."
        ).strip()
    evidence_notes = "No explicit evaluator notes were provided."
    if evaluation_obj:
        notes = "; ".join(evaluation_obj.notes_for_drafting[:6])
        evidence_notes = (
            f"Coverage={evaluation_obj.coverage}; "
            f"recommended_action={evaluation_obj.recommended_action}; "
            f"{notes or 'Use selected evidence only.'}"
        )

    try:
        drafter = get_chat_model(purpose="drafting")
        draft_text = await drafter.ainvoke(
            system_prompt=render_prompt_template("draft_answer", "system"),
            user_prompt=render_prompt_template(
                "draft_answer",
                "user",
                tone=tone,
                tone_guidelines=tone_guidelines,
                question_type=question_type,
                question=question,
                retrieval_plan_summary=retrieval_plan_summary,
                evidence_notes_for_drafting=evidence_notes,
                evidence=evidence_blob,
            ),
        )
        draft_text = normalize_answer_citations(draft_text.strip(), evidence)
        metadata = await extract_draft_metadata(
            question=question,
            question_type=question_type,
            draft_answer=draft_text,
            evidence_blob=evidence_blob,
        )
        confidence_payload = build_structured_confidence_payload(
            metadata=metadata,
            synthesis=synthesis_obj,
            evaluation=evaluation_obj,
            retrieval_strategy_used=retrieval_strategy_used,
            retrieval_notes=existing_confidence,
        )
        return draft_text, render_confidence_notes(confidence_payload), confidence_payload, metadata.model_dump()
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.warning("Draft answer model unavailable; using deterministic fallback error=%s", exc)
        citations = ", ".join(f"[{idx + 1}]" for idx in range(min(4, len(evidence))))
        fallback = (
            "Our renewable and sustainable investing approach focuses on contracted cash-flow assets, "
            "disciplined risk controls, and active asset management across solar and storage platforms. "
            "The strategy integrates ESG screening, due diligence, and ongoing monitoring across the "
            "investment lifecycle, with regulatory and policy risk tracked continuously. "
            f"Key evidence: {citations}."
        )
        metadata = DraftMetadataResult(
            citations_used=extract_answer_citations(fallback),
            coverage_notes="Fallback deterministic draft was used.",
            confidence_notes="Draft generated without live model inference.",
            missing_info_notes=[],
            compliance_flags=[],
        )
        confidence_payload = build_structured_confidence_payload(
            metadata=metadata,
            synthesis=synthesis_obj,
            evaluation=evaluation_obj,
            retrieval_strategy_used=retrieval_strategy_used,
            fallback_score=0.45,
            fallback_compliance="unknown",
            fallback_notes="Draft generated using deterministic fallback due to unavailable model.",
            retrieval_notes=existing_confidence,
        )
        return fallback, render_confidence_notes(confidence_payload), confidence_payload, metadata.model_dump()


async def revise_answer(
    *,
    question: str,
    question_type: str,
    prior_draft: str,
    evidence: list[dict],
    reviewer_feedback: str,
    tone: str,
    retrieval_notes: str,
) -> tuple[str, str, dict, dict, dict]:
    """Generate revised answer based on reviewer feedback and filtered evidence."""

    if not evidence:
        confidence_payload = build_structured_confidence_payload(
            fallback_score=0.1,
            fallback_compliance="needs_review",
            fallback_notes="All evidence was excluded by reviewer; additional source material is required.",
            fallback_gaps=["All available citation chunks were excluded by the reviewer."],
            retrieval_notes=retrieval_notes,
        )
        return (
            "Revision could not be completed because all citation chunks were excluded. "
            "Please provide replacement evidence or relax exclusions.",
            render_confidence_notes(confidence_payload),
            confidence_payload,
            {},
            {},
        )

    evidence_blob = format_evidence_blob(evidence)
    tone_guidelines = get_tone_guidelines(tone)
    revision_intent = await extract_revision_intent(
        question=question,
        reviewer_feedback=reviewer_feedback,
    )

    try:
        reviser = get_chat_model(purpose="revision")
        revised_text = await reviser.ainvoke(
            system_prompt=render_prompt_template("revise_answer", "system"),
            user_prompt=render_prompt_template(
                "revise_answer",
                "user",
                tone=tone,
                tone_guidelines=tone_guidelines,
                question=question,
                reviewer_feedback=reviewer_feedback or "No additional reviewer comments provided.",
                reviewer_intent=revision_intent.reviewer_request_summary,
                prior_draft=prior_draft or "No prior draft available.",
                evidence=evidence_blob,
            ),
        )
        revised_text = normalize_answer_citations(revised_text.strip(), evidence)
        metadata = await extract_draft_metadata(
            question=question,
            question_type=question_type,
            draft_answer=revised_text,
            evidence_blob=evidence_blob,
            purpose="draft_metadata",
        )
        confidence_payload = build_structured_confidence_payload(
            metadata=metadata,
            retrieval_notes=retrieval_notes,
        )
        return (
            revised_text,
            render_confidence_notes(confidence_payload),
            confidence_payload,
            revision_intent.model_dump(),
            metadata.model_dump(),
        )
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.warning("Revision model unavailable; using deterministic fallback error=%s", exc)
        revised_text = (
            f"{prior_draft}\n\nReviewer-requested revision integrated: "
            f"{reviewer_feedback.strip() or 'No additional comments provided.'}"
        )
        revised_text = normalize_answer_citations(revised_text, evidence)
        metadata = DraftMetadataResult(
            citations_used=extract_answer_citations(revised_text),
            coverage_notes="Fallback deterministic revision was used.",
            confidence_notes="Revision generated without live model inference.",
            missing_info_notes=[],
            compliance_flags=[],
        )
        confidence_payload = build_structured_confidence_payload(
            metadata=metadata,
            fallback_score=None,
            fallback_compliance="unknown",
            fallback_notes="Revision produced via fallback because model inference is unavailable.",
            retrieval_notes=retrieval_notes,
        )
        return (
            revised_text,
            render_confidence_notes(confidence_payload),
            confidence_payload,
            revision_intent.model_dump(),
            metadata.model_dump(),
        )


async def polish_answer(
    *,
    question: str,
    question_type: str,
    tone: str,
    draft_answer: str,
    evidence: list[dict],
) -> str:
    """Polish tone with constrained edits while preserving citations."""

    stripped = draft_answer.strip()
    if not stripped:
        return draft_answer

    evidence_blob = format_evidence_blob(evidence)
    tone_guidelines = get_tone_guidelines(tone)
    try:
        polisher = get_chat_model(purpose="polish")
        output = await polisher.ainvoke(
            system_prompt=render_prompt_template("polish_answer", "system"),
            user_prompt=render_prompt_template(
                "polish_answer",
                "user",
                tone=tone,
                tone_guidelines=tone_guidelines,
                question_type=question_type,
                question=question,
                draft_answer=stripped,
                evidence=evidence_blob,
            ),
            temperature=0,
        )
        polished = output.strip()
        if not polished:
            return stripped
        return normalize_answer_citations(polished, evidence)
    except (AIConfigurationError, AIProviderError, RuntimeError, TimeoutError) as exc:
        logger.warning("Tone polish model unavailable; returning unmodified draft error=%s", exc)
        return stripped
