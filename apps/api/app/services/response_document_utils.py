"""Utilities for response-document question parsing and version diffs."""

from __future__ import annotations

import re
from typing import Any
from uuid import UUID

from app.db.models import ResponseDocumentVersion, ResponseQuestion

EXAMPLE_QUESTIONS = [
    "Describe your renewable energy investment strategy and how you create value over the hold period.",
    "How do you assess ESG risks during due diligence and portfolio monitoring?",
    "Provide examples of recent investments in solar or storage infrastructure.",
]

_WORD_SPLIT = re.compile(r"(\s+)")


def extract_questions(raw_text: str) -> list[str]:
    """Extract likely question lines from source text."""

    lines = [line.strip() for line in raw_text.splitlines() if line.strip()]
    cleaned: list[str] = []
    for line in lines:
        candidate = re.sub(r"^[-*\d.)\s]+", "", line).strip()
        if len(candidate) < 10:
            continue
        if candidate.endswith("?") or len(candidate) >= 40:
            cleaned.append(candidate)

    unique: list[str] = []
    seen: set[str] = set()
    for item in cleaned:
        key = item.lower()
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
        if len(unique) >= 30:
            break
    return unique


def normalize_title(text: str) -> str:
    """Create a short title from a question body."""

    words = text.strip().split()
    if not words:
        return "Question"
    joined = " ".join(words[:12])
    return joined if len(words) <= 12 else f"{joined}..."


def coverage_to_score(coverage_value: Any) -> float | None:
    """Map categorical coverage labels to a numeric score."""

    coverage = str(coverage_value or "").strip().lower()
    if coverage == "strong":
        return 1.0
    if coverage == "partial":
        return 0.66
    if coverage == "weak":
        return 0.33
    return None


def tokenize(text: str) -> list[str]:
    """Split text into token chunks while preserving whitespace."""

    return [part for part in _WORD_SPLIT.split(text) if part]


def append_segment(segments: list[dict], kind: str, text: str) -> None:
    """Merge adjacent diff segments of the same kind."""

    if not text:
        return
    if segments and segments[-1]["kind"] == kind:
        segments[-1]["text"] = f"{segments[-1]['text']}{text}"
        return
    segments.append({"kind": kind, "text": text})


def build_diff_segments(left_text: str, right_text: str) -> list[dict]:
    """Build a lightweight word-preserving diff payload."""

    left = tokenize(left_text)
    right = tokenize(right_text)
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
            append_segment(segments, "same", right[j])
            i += 1
            j += 1
            continue
        if dp[i + 1][j] >= dp[i][j + 1]:
            append_segment(segments, "removed", left[i])
            i += 1
        else:
            append_segment(segments, "added", right[j])
            j += 1

    while i < len(left):
        append_segment(segments, "removed", left[i])
        i += 1
    while j < len(right):
        append_segment(segments, "added", right[j])
        j += 1
    return segments


def section_text_map(version: ResponseDocumentVersion) -> dict[UUID, str]:
    """Map question ids to section content for a specific version."""

    return {section.question_id: section.content_markdown for section in version.sections}


def compose_document_text(questions: list[ResponseQuestion], section_text: dict[UUID, str]) -> str:
    """Create a unified markdown-style text for whole-document diffing."""

    blocks: list[str] = []
    for question in sorted(questions, key=lambda item: item.order_index):
        blocks.append(f"## {question.extracted_text}\n{section_text.get(question.id, '').strip()}")
    return "\n\n".join(blocks).strip()
