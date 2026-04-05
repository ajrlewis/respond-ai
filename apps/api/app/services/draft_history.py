"""Draft history helpers for session snapshots and comparisons."""

from __future__ import annotations

from datetime import UTC, datetime
import re
from typing import Any

from app.db.models import RFPSession


def _as_float(value: Any) -> float | None:
    if value is None:
        return None
    if isinstance(value, (float, int)):
        return float(value)
    try:
        return float(str(value))
    except ValueError:
        return None


def _tokenize(text: str) -> list[str]:
    return [part for part in re.split(r"(\s+)", text) if part]


def _build_diff_segments(left_text: str, right_text: str) -> list[dict]:
    left = _tokenize(left_text)
    right = _tokenize(right_text)
    dp: list[list[int]] = [[0] * (len(right) + 1) for _ in range(len(left) + 1)]

    for i in range(len(left) - 1, -1, -1):
        for j in range(len(right) - 1, -1, -1):
            if left[i] == right[j]:
                dp[i][j] = dp[i + 1][j + 1] + 1
            else:
                dp[i][j] = max(dp[i + 1][j], dp[i][j + 1])

    segments: list[dict] = []
    i = 0
    j = 0
    while i < len(left) and j < len(right):
        if left[i] == right[j]:
            _append_segment(segments, "same", right[j])
            i += 1
            j += 1
            continue
        if dp[i + 1][j] >= dp[i][j + 1]:
            _append_segment(segments, "removed", left[i])
            i += 1
        else:
            _append_segment(segments, "added", right[j])
            j += 1

    while i < len(left):
        _append_segment(segments, "removed", left[i])
        i += 1
    while j < len(right):
        _append_segment(segments, "added", right[j])
        j += 1

    return segments


def _append_segment(segments: list[dict], kind: str, text: str) -> None:
    if not text:
        return
    if segments and segments[-1]["kind"] == kind:
        segments[-1]["text"] = f"{segments[-1]['text']}{text}"
        return
    segments.append({"kind": kind, "text": text})


def list_session_drafts(session: RFPSession) -> list[dict]:
    """Normalize and label session draft snapshots for UI/API usage."""

    raw_versions = getattr(session, "answer_versions_payload", []) or []
    normalized: list[dict] = []

    for index, item in enumerate(raw_versions, start=1):
        if not isinstance(item, dict):
            continue
        version_number = int(item.get("version_number") or index)
        version_id = str(item.get("version_id") or f"draft-{version_number}")
        answer_text = str(item.get("answer_text") or item.get("content") or "").strip()
        if not answer_text:
            continue

        stage = str(item.get("stage") or "draft")
        if stage not in {"draft", "revision", "final"}:
            stage = "draft"

        normalized.append(
            {
                "version_id": version_id,
                "version_number": version_number,
                "label": str(item.get("label") or f"Draft {version_number}"),
                "stage": stage,
                "answer_text": answer_text,
                "content": answer_text,
                "status": str(item.get("status") or ("approved" if stage == "final" else "draft")),
                "revision_feedback": str(item.get("revision_feedback") or "").strip() or None,
                "included_chunk_ids": [str(chunk_id) for chunk_id in (item.get("included_chunk_ids") or [])],
                "excluded_chunk_ids": [str(chunk_id) for chunk_id in (item.get("excluded_chunk_ids") or [])],
                "question_type": item.get("question_type"),
                "confidence_notes": str(item.get("confidence_notes") or "").strip() or None,
                "confidence_score": _as_float(item.get("confidence_score")),
                "created_at": item.get("created_at")
                or getattr(session, "updated_at", None)
                or datetime.now(UTC).isoformat(),
            }
        )

    normalized.sort(
        key=lambda draft: (
            int(draft.get("version_number", 0)),
            str(draft.get("created_at") or ""),
        )
    )

    if not normalized:
        return []

    latest = normalized[-1]
    session_is_approved = getattr(session, "status", "") == "approved"

    for draft in normalized:
        is_latest = draft["version_id"] == latest["version_id"]
        if session_is_approved and is_latest:
            draft["status"] = "approved"
            draft["is_current"] = True
            draft["is_approved"] = True
            draft["label"] = f"Final (Approved · Draft {draft['version_number']})"
            continue
        if is_latest:
            draft["status"] = "draft"
            draft["is_current"] = True
            draft["is_approved"] = False
            draft["label"] = f"Draft {draft['version_number']} (current)"
            continue

        draft["status"] = "historical"
        draft["is_current"] = False
        draft["is_approved"] = False
        draft["label"] = f"Draft {draft['version_number']} (historical)"

    return normalized


def get_session_draft(session: RFPSession, draft_id: str) -> dict | None:
    """Fetch a specific normalized draft by id."""

    for draft in list_session_drafts(session):
        if draft["version_id"] == draft_id:
            return draft
    return None


def compare_session_drafts(session: RFPSession, left_id: str, right_id: str) -> dict | None:
    """Compare two drafts by id and return a structured diff."""

    drafts = list_session_drafts(session)
    lookup = {item["version_id"]: item for item in drafts}
    left = lookup.get(left_id)
    right = lookup.get(right_id)
    if not left or not right:
        return None

    return {
        "left": left,
        "right": right,
        "segments": _build_diff_segments(left["content"], right["content"]),
    }
