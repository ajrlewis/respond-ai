"""Confidence and evidence-text helpers for drafting/evaluation flows."""

from __future__ import annotations

from typing import Literal

from app.ai.schemas import DraftMetadataResult, EvidenceEvaluationResult, EvidenceSynthesisResult


def format_evidence_blob(evidence: list[dict]) -> str:
    """Format retrieved evidence chunks into a deterministic, citeable block."""

    return "\n\n".join(
        (
            f"[{idx + 1}] source={item.get('document_filename', 'unknown')}#chunk-{item.get('chunk_index', 'n/a')}\n"
            f"{item.get('text', '')}"
        )
        for idx, item in enumerate(evidence)
    )


def build_structured_confidence_payload(
    *,
    metadata: DraftMetadataResult | None = None,
    synthesis: EvidenceSynthesisResult | None = None,
    evaluation: EvidenceEvaluationResult | None = None,
    retrieval_strategy_used: str | None = None,
    retrieval_notes: str = "",
    fallback_score: float | None = None,
    fallback_compliance: Literal["passed", "needs_review", "unknown"] = "unknown",
    fallback_notes: str = "",
    fallback_gaps: list[str] | None = None,
) -> dict:
    """Build structured confidence metadata for API and UI rendering."""

    if metadata:
        missing_info = list(metadata.missing_info_notes)
        if synthesis:
            missing_info = sorted(
                {
                    item.strip()
                    for item in [*missing_info, *synthesis.missing_information]
                    if isinstance(item, str) and item.strip()
                }
            )
        if evaluation:
            missing_info = sorted(
                {
                    item.strip()
                    for item in [*missing_info, *evaluation.missing_information]
                    if isinstance(item, str) and item.strip()
                }
            )
        score = float(evaluation.confidence) if evaluation else 0.78
        if evaluation and evaluation.coverage == "partial":
            score -= 0.08
        if evaluation and evaluation.coverage == "weak":
            score -= 0.2
        if missing_info:
            score -= 0.18
        if metadata.compliance_flags:
            score -= 0.18
        score = max(0.0, min(1.0, score))
        return {
            "score": round(score, 2),
            "compliance_status": "needs_review" if metadata.compliance_flags else "passed",
            "model_notes": metadata.confidence_notes.strip(),
            "retrieval_notes": retrieval_notes.strip(),
            "evidence_gaps": missing_info,
            "retrieval_strategy": (retrieval_strategy_used or "").strip() or None,
            "coverage": evaluation.coverage if evaluation else "unknown",
            "recommended_action": evaluation.recommended_action if evaluation else "unknown",
            "selected_chunk_ids": list(evaluation.selected_chunk_ids) if evaluation else [],
            "rejected_chunk_ids": list(evaluation.rejected_chunk_ids) if evaluation else [],
            "notes_for_drafting": list(evaluation.notes_for_drafting) if evaluation else [],
        }

    coverage = evaluation.coverage if evaluation else "unknown"
    recommended_action = evaluation.recommended_action if evaluation else "unknown"
    return {
        "score": (
            float(evaluation.confidence)
            if evaluation and isinstance(evaluation.confidence, (float, int))
            else fallback_score
        ),
        "compliance_status": fallback_compliance,
        "model_notes": fallback_notes.strip(),
        "retrieval_notes": retrieval_notes.strip(),
        "evidence_gaps": sorted(
            {
                item.strip()
                for item in [*(fallback_gaps or []), *(evaluation.missing_information if evaluation else [])]
                if isinstance(item, str) and item.strip()
            }
        ),
        "retrieval_strategy": (retrieval_strategy_used or "").strip() or None,
        "coverage": coverage,
        "recommended_action": recommended_action,
        "selected_chunk_ids": list(evaluation.selected_chunk_ids) if evaluation else [],
        "rejected_chunk_ids": list(evaluation.rejected_chunk_ids) if evaluation else [],
        "notes_for_drafting": list(evaluation.notes_for_drafting) if evaluation else [],
    }


def render_confidence_notes(confidence_payload: dict) -> str:
    """Render a readable confidence summary from structured payload."""

    notes = [
        (
            f"Confidence score (heuristic): {confidence_payload['score']:.2f}."
            if isinstance(confidence_payload.get("score"), (float, int))
            else "Confidence score (heuristic): Not available."
        ),
        (
            "Compliance status: Passed."
            if confidence_payload.get("compliance_status") == "passed"
            else (
                "Compliance status: Needs review."
                if confidence_payload.get("compliance_status") == "needs_review"
                else "Compliance status: Unknown."
            )
        ),
    ]

    model_notes = str(confidence_payload.get("model_notes", "")).strip()
    if model_notes:
        notes.append(f"Model notes: {model_notes}")

    evidence_gaps = [gap for gap in confidence_payload.get("evidence_gaps", []) if isinstance(gap, str) and gap.strip()]
    if evidence_gaps:
        notes.append(f"Evidence gaps: {'; '.join(evidence_gaps)}")

    retrieval_notes = str(confidence_payload.get("retrieval_notes", "")).strip()
    if retrieval_notes:
        notes.append(f"Retrieval notes: {retrieval_notes}")

    retrieval_strategy = str(confidence_payload.get("retrieval_strategy", "")).strip()
    if retrieval_strategy:
        notes.append(f"Retrieval strategy: {retrieval_strategy}.")

    coverage = str(confidence_payload.get("coverage", "")).strip()
    if coverage:
        notes.append(f"Evidence coverage: {coverage}.")

    return " ".join(notes)
