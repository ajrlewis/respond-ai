"""Finalization and answer-version helpers for review approval."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal

from app.graph.state import WorkflowState
from app.services.evidence_analysis import active_evidence, evidence_item_key


def append_answer_version(
    existing_versions: list[dict],
    answer_text: str,
    stage: Literal["draft", "revision", "final"],
    *,
    question_type: str | None = None,
    confidence_notes: str = "",
    confidence_payload: dict | None = None,
    revision_feedback: str = "",
    included_chunk_ids: list[str] | None = None,
    excluded_chunk_ids: list[str] | None = None,
) -> list[dict]:
    """Append immutable answer snapshots while skipping duplicate adjacent text."""

    normalized_answer = answer_text.strip()
    if not normalized_answer:
        return existing_versions

    if existing_versions and existing_versions[-1].get("answer_text", "").strip() == normalized_answer:
        return existing_versions

    existing_numbers = [
        int(item.get("version_number", 0))
        for item in existing_versions
        if isinstance(item, dict) and str(item.get("version_number", "")).isdigit()
    ]
    next_index = (max(existing_numbers) if existing_numbers else len(existing_versions)) + 1
    label = f"Draft {next_index}" if stage != "final" else "Final"
    score = confidence_payload.get("score") if isinstance(confidence_payload, dict) else None
    snapshot = {
        "version_id": str(uuid.uuid4()),
        "version_number": next_index,
        "label": label,
        "stage": stage,
        "answer_text": normalized_answer,
        "content": normalized_answer,
        "status": "approved" if stage == "final" else "draft",
        "revision_feedback": revision_feedback.strip() or None,
        "included_chunk_ids": list(included_chunk_ids or []),
        "excluded_chunk_ids": list(excluded_chunk_ids or []),
        "question_type": question_type,
        "confidence_notes": confidence_notes.strip() or None,
        "confidence_score": float(score) if isinstance(score, (int, float)) else None,
        "created_at": datetime.now(UTC).isoformat(),
    }
    return [*existing_versions, snapshot]


def latest_version_index(versions: list[dict]) -> int | None:
    """Return the index of the latest version row by version_number."""

    best_index: int | None = None
    best_number = -1
    for index, item in enumerate(versions):
        if not isinstance(item, dict):
            continue
        raw = item.get("version_number")
        if isinstance(raw, int):
            number = raw
        elif isinstance(raw, str) and raw.isdigit():
            number = int(raw)
        else:
            number = index + 1
        if number >= best_number:
            best_number = number
            best_index = index
    return best_index


def audit_evidence_rows(evidence: list[dict]) -> list[dict]:
    """Normalize evidence rows for immutable audit snapshots."""

    rows: list[dict] = []
    for item in evidence:
        rows.append(
            {
                "chunk_id": str(item.get("chunk_id", "")).strip() or None,
                "document_id": str(item.get("document_id", "")).strip() or None,
                "document_title": str(item.get("document_title", "")).strip(),
                "document_filename": str(item.get("document_filename", "")).strip(),
                "chunk_index": item.get("chunk_index"),
                "score": item.get("score"),
                "retrieval_method": str(item.get("retrieval_method", "")).strip(),
                "text": str(item.get("text", "")).strip(),
                "excluded_by_reviewer": bool(item.get("excluded_by_reviewer", False)),
                "metadata": item.get("metadata", {}) if isinstance(item.get("metadata"), dict) else {},
            }
        )
    return rows


@dataclass(slots=True)
class FinalizationArtifacts:
    """Prepared fields to persist during approval finalization."""

    final_answer: str
    final_version_number: int | None
    reviewer_id: str | None
    next_versions: list[dict]
    final_audit_payload: dict


def build_finalization_artifacts(
    *,
    session,
    state: WorkflowState,
    review_rows: list,
    approved_at: datetime,
) -> FinalizationArtifacts:
    """Build immutable finalization artifacts from session state + review history."""

    final_answer = (getattr(session, "draft_answer", None) or state.get("draft_answer", "")).strip()
    if not final_answer:
        final_answer = str(state.get("edited_answer", "")).strip()

    evidence_for_snapshot = state.get("curated_evidence", []) or list(getattr(session, "evidence_payload", []) or [])
    included_chunk_ids = [
        evidence_item_key(item)
        for item in active_evidence(evidence_for_snapshot)
    ]
    excluded_chunk_ids = [
        evidence_item_key(item)
        for item in evidence_for_snapshot
        if bool(item.get("excluded_by_reviewer", False))
    ]

    existing_versions = list(getattr(session, "answer_versions_payload", []) or [])
    latest_index = latest_version_index(existing_versions)
    if latest_index is None:
        next_versions = append_answer_version(
            existing_versions,
            final_answer,
            "final",
            question_type=state.get("question_type"),
            confidence_notes=state.get("confidence_notes", ""),
            confidence_payload=state.get("confidence_payload", {}),
            revision_feedback=state.get("review_comments", ""),
            included_chunk_ids=included_chunk_ids,
            excluded_chunk_ids=excluded_chunk_ids,
        )
        latest_index = latest_version_index(next_versions)
    else:
        next_versions = []
        for index, item in enumerate(existing_versions):
            if not isinstance(item, dict):
                next_versions.append(item)
                continue
            row = {**item}
            is_latest = index == latest_index
            row["status"] = "approved" if is_latest else "historical"
            if is_latest:
                row["stage"] = "final"
                row["answer_text"] = final_answer
                row["content"] = final_answer
                row["included_chunk_ids"] = included_chunk_ids
                row["excluded_chunk_ids"] = excluded_chunk_ids
                if state.get("review_comments"):
                    row["revision_feedback"] = state.get("review_comments", "")
                score = (state.get("confidence_payload") or {}).get("score")
                row["confidence_score"] = float(score) if isinstance(score, (int, float)) else None
                row["confidence_notes"] = state.get("confidence_notes", "") or None
            next_versions.append(row)

    if latest_index is None:
        final_version_number: int | None = None
    else:
        latest_row = next_versions[latest_index] if latest_index < len(next_versions) else {}
        if isinstance(latest_row, dict) and str(latest_row.get("version_number", "")).isdigit():
            final_version_number = int(str(latest_row.get("version_number")))
        elif isinstance(latest_row, dict) and isinstance(latest_row.get("version_number"), int):
            final_version_number = int(latest_row.get("version_number"))
        else:
            final_version_number = latest_index + 1

    review_history = [
        {
            "id": str(item.id),
            "reviewer_action": item.reviewer_action,
            "reviewer_id": item.reviewer_id,
            "review_comments": item.review_comments,
            "edited_answer": item.edited_answer,
            "excluded_evidence_keys": list(item.excluded_evidence_keys or []),
            "reviewed_evidence_gaps": bool(item.reviewed_evidence_gaps),
            "evidence_gaps_acknowledged_at": (
                item.evidence_gaps_acknowledged_at.isoformat()
                if getattr(item, "evidence_gaps_acknowledged_at", None)
                else None
            ),
            "created_at": item.created_at.isoformat(),
        }
        for item in review_rows
    ]

    reviewer_id = str(state.get("reviewer_id", "")).strip() or None
    if not reviewer_id:
        for event in reversed(review_history):
            if event.get("reviewer_action") == "approve" and event.get("reviewer_id"):
                reviewer_id = str(event.get("reviewer_id"))
                break

    final_audit_payload = {
        "version_number": final_version_number,
        "timestamp": approved_at.isoformat(),
        "reviewer_action": "approve",
        "reviewer_id": reviewer_id,
        "final_answer": final_answer,
        "included_chunk_ids": included_chunk_ids,
        "excluded_chunk_ids": excluded_chunk_ids,
        "selected_evidence": audit_evidence_rows(active_evidence(evidence_for_snapshot)),
        "retrieval_plan": state.get("retrieval_plan") or getattr(session, "retrieval_plan_payload", {}) or {},
        "retrieval_strategy": (
            state.get("retrieval_strategy_used")
            or getattr(session, "retrieval_strategy_used", None)
        ),
        "evidence_evaluation": (
            state.get("evidence_evaluation")
            or getattr(session, "evidence_evaluation_payload", {}) or {}
        ),
        "retry_count": int(
            state.get("retry_count")
            if state.get("retry_count") is not None
            else getattr(session, "retry_count", 0)
        ),
        "selected_chunk_ids": list(
            {
                str(item.get("chunk_id", "")).strip() or evidence_item_key(item)
                for item in (getattr(session, "selected_evidence_payload", []) or [])
                if isinstance(item, dict)
            }
        ),
        "rejected_chunk_ids": list(
            {
                str(item.get("chunk_id", "")).strip() or evidence_item_key(item)
                for item in (getattr(session, "rejected_evidence_payload", []) or [])
                if isinstance(item, dict)
            }
        ),
        "confidence_score": (state.get("confidence_payload") or {}).get("score"),
        "confidence_notes": state.get("confidence_notes", ""),
        "confidence_payload": state.get("confidence_payload", {}) or {},
        "evidence_gap_count": len((state.get("confidence_payload") or {}).get("evidence_gaps", []) or []),
        "evidence_gaps_acknowledged": bool(getattr(session, "evidence_gaps_acknowledged", False)),
        "evidence_gaps_acknowledged_at": (
            session.evidence_gaps_acknowledged_at.isoformat()
            if getattr(session, "evidence_gaps_acknowledged_at", None)
            else None
        ),
        "review_history": review_history,
    }
    return FinalizationArtifacts(
        final_answer=final_answer,
        final_version_number=final_version_number,
        reviewer_id=reviewer_id,
        next_versions=next_versions,
        final_audit_payload=final_audit_payload,
    )
