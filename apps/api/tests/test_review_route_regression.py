import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.routes import review as review_route
from app.schemas.reviews import ReviewRequest


class _ExpiringSession:
    def __init__(self, thread_id: str) -> None:
        self._thread_id = thread_id
        self.expired = False

    @property
    def graph_thread_id(self) -> str:
        if self.expired:
            raise RuntimeError("Expired ORM attribute access")
        return self._thread_id


def test_review_route_uses_thread_id_before_review_commit(monkeypatch) -> None:
    session_id = uuid4()
    initial_session = _ExpiringSession(thread_id="thread-123")
    now = datetime.now(UTC)
    refreshed_session = SimpleNamespace(
        id=session_id,
        graph_thread_id="thread-123",
        question_text="How do you manage risk?",
        question_type="risk",
        tone="formal",
        status="approved",
        current_node="finalize_response",
        draft_answer="Draft",
        final_answer="Final",
        confidence_notes="ok",
        evidence_payload=[],
        created_at=now,
        updated_at=now,
    )

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db
            self._calls = 0

        async def get_session(self, incoming_session_id):
            assert incoming_session_id == session_id
            self._calls += 1
            return initial_session if self._calls == 1 else refreshed_session

    class FakeReviewService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_review(self, **kwargs):
            initial_session.expired = True
            return SimpleNamespace(id=uuid4())

    resume_calls: list[tuple[str, dict]] = []

    async def fake_resume_from_review(*, thread_id: str, review_payload: dict) -> dict:
        resume_calls.append((thread_id, review_payload))
        return {}

    class FakeDB:
        async def refresh(self, obj) -> None:
            return None

    monkeypatch.setattr(review_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(review_route, "ReviewService", FakeReviewService)
    monkeypatch.setattr(review_route, "resume_from_review", fake_resume_from_review)

    payload = ReviewRequest(reviewer_action="approve")
    result = asyncio.run(review_route.review_session(session_id=session_id, payload=payload, db=FakeDB()))

    assert resume_calls
    assert resume_calls[0][0] == "thread-123"
    assert result.session.id == session_id


def test_review_route_allows_revise_with_excluded_evidence(monkeypatch) -> None:
    session_id = uuid4()
    now = datetime.now(UTC)
    session = SimpleNamespace(
        id=session_id,
        graph_thread_id="thread-456",
        confidence_payload={"evidence_gaps": []},
        question_text="Question",
        question_type="risk",
        tone="formal",
        status="awaiting_review",
        current_node="human_review",
        draft_answer="Draft",
        final_answer=None,
        confidence_notes="ok",
        evidence_payload=[],
        created_at=now,
        updated_at=now,
    )

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, incoming_session_id):
            assert incoming_session_id == session_id
            return session

    class FakeReviewService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_review(self, **kwargs):
            return SimpleNamespace(id=uuid4())

    resume_calls: list[tuple[str, dict]] = []

    async def fake_resume_from_review(*, thread_id: str, review_payload: dict) -> dict:
        resume_calls.append((thread_id, review_payload))
        return {}

    class FakeDB:
        async def refresh(self, obj) -> None:
            return None

    monkeypatch.setattr(review_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(review_route, "ReviewService", FakeReviewService)
    monkeypatch.setattr(review_route, "resume_from_review", fake_resume_from_review)

    payload = ReviewRequest(
        reviewer_action="revise",
        excluded_evidence_keys=["chunk-1"],
    )
    result = asyncio.run(review_route.review_session(session_id=session_id, payload=payload, db=FakeDB()))

    assert resume_calls
    assert resume_calls[0][1]["excluded_evidence_keys"] == ["chunk-1"]
    assert result.session.id == session_id


def test_review_route_blocks_approve_when_gaps_not_acknowledged(monkeypatch) -> None:
    session_id = uuid4()
    session = SimpleNamespace(
        id=session_id,
        graph_thread_id="thread-789",
        confidence_payload={"evidence_gaps": ["Missing quantitative metrics."]},
    )

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, incoming_session_id):
            assert incoming_session_id == session_id
            return session

    class FakeReviewService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_review(self, **kwargs):
            raise AssertionError("create_review should not be called when approval is blocked")

    class FakeDB:
        async def refresh(self, obj) -> None:
            return None

    monkeypatch.setattr(review_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(review_route, "ReviewService", FakeReviewService)

    payload = ReviewRequest(reviewer_action="approve", reviewed_evidence_gaps=False)
    try:
        asyncio.run(review_route.review_session(session_id=session_id, payload=payload, db=FakeDB()))
        raise AssertionError("Expected HTTPException for unacknowledged evidence gaps")
    except HTTPException as exc:
        assert exc.status_code == 400
        assert exc.detail == "Evidence gaps must be acknowledged before approval."


def test_review_route_allows_approve_when_gaps_already_acknowledged(monkeypatch) -> None:
    session_id = uuid4()
    now = datetime.now(UTC)
    session = SimpleNamespace(
        id=session_id,
        graph_thread_id="thread-ack",
        confidence_payload={"evidence_gaps": ["Missing quantitative metrics."]},
        evidence_gaps_acknowledged=True,
        question_text="Question",
        question_type="risk",
        tone="formal",
        status="awaiting_review",
        current_node="human_review",
        draft_answer="Draft",
        final_answer=None,
        confidence_notes="ok",
        evidence_payload=[],
        created_at=now,
        updated_at=now,
    )
    create_calls: list[dict] = []

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, incoming_session_id):
            assert incoming_session_id == session_id
            return session

    class FakeReviewService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_review(self, **kwargs):
            create_calls.append(kwargs)
            return SimpleNamespace(id=uuid4())

    resume_calls: list[tuple[str, dict]] = []

    async def fake_resume_from_review(*, thread_id: str, review_payload: dict) -> dict:
        resume_calls.append((thread_id, review_payload))
        return {}

    class FakeDB:
        async def refresh(self, obj) -> None:
            return None

    monkeypatch.setattr(review_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(review_route, "ReviewService", FakeReviewService)
    monkeypatch.setattr(review_route, "resume_from_review", fake_resume_from_review)

    result = asyncio.run(review_route.review_session(session_id=session_id, payload=ReviewRequest(reviewer_action="approve"), db=FakeDB()))

    assert result.session.id == session_id
    assert create_calls
    assert create_calls[0]["evidence_gaps_acknowledged"] is True
    assert resume_calls


def test_review_route_blocks_actions_after_approval(monkeypatch) -> None:
    session_id = uuid4()
    session = SimpleNamespace(
        id=session_id,
        graph_thread_id="thread-999",
        status="approved",
        confidence_payload={"evidence_gaps": []},
    )

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, incoming_session_id):
            assert incoming_session_id == session_id
            return session

    class FakeReviewService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_review(self, **kwargs):
            raise AssertionError("create_review should not be called for locked sessions")

    class FakeDB:
        async def refresh(self, obj) -> None:
            return None

    monkeypatch.setattr(review_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(review_route, "ReviewService", FakeReviewService)

    try:
        asyncio.run(
            review_route.review_session(
                session_id=session_id,
                payload=ReviewRequest(reviewer_action="revise", review_comments="Needs edits."),
                db=FakeDB(),
            )
        )
        raise AssertionError("Expected HTTPException for approved locked session")
    except HTTPException as exc:
        assert exc.status_code == 409
        assert "locked" in str(exc.detail).lower()
