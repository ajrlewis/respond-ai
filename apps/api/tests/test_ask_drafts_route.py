import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.routes import ask as ask_route


def _session_payload(status: str = "awaiting_review") -> SimpleNamespace:
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        graph_thread_id="thread-1",
        question_text="How do you manage risk?",
        question_type="risk",
        tone="formal",
        status=status,
        current_node="human_review",
        draft_answer="Draft",
        final_answer="Final" if status == "approved" else None,
        final_version_number=2 if status == "approved" else None,
        approved_at=now if status == "approved" else None,
        reviewer_action="approve" if status == "approved" else None,
        reviewer_id="reviewer-1" if status == "approved" else None,
        confidence_notes="ok",
        confidence_payload={},
        evidence_payload=[],
        final_audit_payload=(
            {
                "version_number": 2,
                "timestamp": now.isoformat(),
                "reviewer_action": "approve",
                "reviewer_id": "reviewer-1",
                "final_answer": "Final",
                "included_chunk_ids": ["chunk-1"],
                "excluded_chunk_ids": [],
                "selected_evidence": [
                    {
                        "chunk_id": "chunk-1",
                        "document_id": str(uuid4()),
                        "document_title": "Policy",
                        "document_filename": "policy.md",
                        "chunk_index": 4,
                        "score": 0.91,
                        "retrieval_method": "semantic",
                        "text": "Evidence text.",
                        "excluded_by_reviewer": False,
                        "metadata": {},
                    }
                ],
                "confidence_score": 0.86,
                "confidence_notes": "Strong grounding.",
                "confidence_payload": {"score": 0.86},
                "review_history": [
                    {
                        "id": str(uuid4()),
                        "reviewer_action": "approve",
                        "reviewer_id": "reviewer-1",
                        "review_comments": "Looks good.",
                        "edited_answer": None,
                        "excluded_evidence_keys": [],
                        "reviewed_evidence_gaps": True,
                        "created_at": now.isoformat(),
                    }
                ],
            }
            if status == "approved"
            else {}
        ),
        answer_versions_payload=[
            {
                "version_id": "d1",
                "version_number": 1,
                "answer_text": "Initial draft text.",
                "stage": "draft",
                "created_at": now.isoformat(),
            },
            {
                "version_id": "d2",
                "version_number": 2,
                "answer_text": "Revised draft text with added controls.",
                "stage": "revision",
                "revision_feedback": "Add detail on controls.",
                "created_at": now.isoformat(),
            },
        ],
        created_at=now,
        updated_at=now,
    )


def test_list_drafts_route_returns_normalized_snapshots(monkeypatch) -> None:
    session = _session_payload()

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, session_id):
            assert session_id == session.id
            return session

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)

    drafts = asyncio.run(ask_route.list_drafts(session_id=session.id, db=object()))

    assert len(drafts) == 2
    assert drafts[0].status == "historical"
    assert drafts[1].status == "draft"
    assert drafts[1].is_current is True


def test_get_draft_route_returns_single_snapshot(monkeypatch) -> None:
    session = _session_payload()

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, session_id):
            assert session_id == session.id
            return session

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)

    draft = asyncio.run(ask_route.get_draft(session_id=session.id, draft_id="d2", db=object()))

    assert draft.version_number == 2
    assert draft.revision_feedback == "Add detail on controls."


def test_compare_drafts_route_returns_diff(monkeypatch) -> None:
    session = _session_payload()

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, session_id):
            assert session_id == session.id
            return session

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)

    comparison = asyncio.run(ask_route.compare_drafts(session_id=session.id, left="d1", right="d2", db=object()))

    assert comparison.left.version_id == "d1"
    assert comparison.right.version_id == "d2"
    assert any(segment.kind == "added" for segment in comparison.segments)


def test_get_draft_route_raises_not_found_for_unknown_id(monkeypatch) -> None:
    session = _session_payload()

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, session_id):
            assert session_id == session.id
            return session

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)

    try:
        asyncio.run(ask_route.get_draft(session_id=session.id, draft_id="missing", db=object()))
        raise AssertionError("Expected HTTPException for missing draft id")
    except HTTPException as exc:
        assert exc.status_code == 404


def test_get_final_audit_route_returns_snapshot_for_approved_session(monkeypatch) -> None:
    session = _session_payload(status="approved")

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, session_id):
            assert session_id == session.id
            return session

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)

    audit = asyncio.run(ask_route.get_final_audit(session_id=session.id, db=object()))

    assert audit.session_id == session.id
    assert audit.version_number == 2
    assert audit.reviewer_action == "approve"
    assert audit.reviewer_id == "reviewer-1"
    assert audit.final_answer == "Final"
    assert audit.included_chunk_ids == ["chunk-1"]
    assert len(audit.selected_evidence) == 1
    assert len(audit.review_history) == 1


def test_get_final_audit_route_rejects_non_approved_session(monkeypatch) -> None:
    session = _session_payload(status="awaiting_review")

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, session_id):
            assert session_id == session.id
            return session

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)

    try:
        asyncio.run(ask_route.get_final_audit(session_id=session.id, db=object()))
        raise AssertionError("Expected HTTPException for non-approved session")
    except HTTPException as exc:
        assert exc.status_code == 409
