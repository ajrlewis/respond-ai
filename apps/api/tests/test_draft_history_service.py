from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from app.services.draft_history import compare_session_drafts, get_session_draft, list_session_drafts


def _build_session(status: str = "awaiting_review") -> SimpleNamespace:
    now = datetime.now(UTC).isoformat()
    return SimpleNamespace(
        id=uuid4(),
        status=status,
        answer_versions_payload=[
            {
                "version_id": "d1",
                "version_number": 1,
                "stage": "draft",
                "answer_text": "Alpha risk controls [1].",
                "created_at": now,
            },
            {
                "version_id": "d2",
                "version_number": 2,
                "stage": "revision",
                "answer_text": "Alpha risk controls [1] and ESG oversight [2].",
                "created_at": now,
                "revision_feedback": "Add ESG references.",
                "excluded_chunk_ids": ["chunk-x"],
            },
        ],
    )


def test_list_session_drafts_marks_current_and_historical() -> None:
    session = _build_session(status="awaiting_review")
    drafts = list_session_drafts(session)

    assert len(drafts) == 2
    assert drafts[0]["status"] == "historical"
    assert drafts[0]["label"] == "Draft 1 (historical)"
    assert drafts[1]["status"] == "draft"
    assert drafts[1]["is_current"] is True
    assert drafts[1]["label"] == "Draft 2 (current)"


def test_list_session_drafts_marks_latest_as_approved_when_session_approved() -> None:
    session = _build_session(status="approved")
    drafts = list_session_drafts(session)

    assert drafts[-1]["status"] == "approved"
    assert drafts[-1]["is_approved"] is True
    assert drafts[-1]["label"] == "Final (Approved · Draft 2)"


def test_get_session_draft_finds_by_id() -> None:
    session = _build_session()
    draft = get_session_draft(session, "d2")

    assert draft is not None
    assert draft["version_number"] == 2
    assert draft["revision_feedback"] == "Add ESG references."


def test_compare_session_drafts_returns_structured_segments() -> None:
    session = _build_session()
    comparison = compare_session_drafts(session, "d1", "d2")

    assert comparison is not None
    assert comparison["left"]["version_id"] == "d1"
    assert comparison["right"]["version_id"] == "d2"
    assert any(segment["kind"] == "added" for segment in comparison["segments"])
