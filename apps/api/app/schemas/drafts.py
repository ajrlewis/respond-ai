"""Draft history endpoint schemas."""

from typing import Literal

from pydantic import BaseModel

from app.schemas.sessions import AnswerVersionOut


class DraftDiffSegmentOut(BaseModel):
    """Single diff segment between two draft versions."""

    kind: Literal["same", "added", "removed"]
    text: str


class DraftCompareOut(BaseModel):
    """Comparison payload for two selected drafts."""

    left: AnswerVersionOut
    right: AnswerVersionOut
    segments: list[DraftDiffSegmentOut]
