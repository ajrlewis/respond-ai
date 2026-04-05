import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

from fastapi import HTTPException

from app.routes import ask as ask_route
from app.schemas.sessions import AskRequest


class _FakeWorkflowEventBus:
    def __init__(self) -> None:
        self.registered: list[tuple[str, str]] = []
        self.thread_events: list[dict] = []
        self.session_events: list[dict] = []

    async def register_thread_session(self, *, thread_id: str, session_id: str) -> None:
        self.registered.append((thread_id, session_id))

    async def publish_thread(self, **kwargs) -> None:
        self.thread_events.append(kwargs)

    async def publish_session(self, **kwargs) -> None:
        self.session_events.append(kwargs)


def _build_session(thread_id: str):
    now = datetime.now(UTC)
    return SimpleNamespace(
        id=uuid4(),
        graph_thread_id=thread_id,
        question_text="How do you manage risk?",
        question_type="risk",
        tone="formal",
        status="draft",
        current_node="ask",
        retrieval_strategy_used=None,
        retry_count=0,
        draft_answer=None,
        final_answer=None,
        final_version_number=None,
        approved_at=None,
        reviewer_action=None,
        reviewer_id=None,
        evidence_gaps_acknowledged=False,
        evidence_gaps_acknowledged_at=None,
        confidence_notes="",
        confidence_payload={},
        retrieval_plan_payload={},
        evidence_evaluation_payload={},
        evidence_payload=[],
        answer_versions_payload=[],
        final_audit_payload={},
        created_at=now,
        updated_at=now,
    )


def test_ask_route_enqueues_background_task(monkeypatch) -> None:
    thread_id = "thread-123"
    fake_session = _build_session(thread_id)
    enqueue_calls: list[dict] = []
    event_bus = _FakeWorkflowEventBus()

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_or_get_session(self, *, thread_id: str, question_text: str, tone: str):
            assert thread_id == "thread-123"
            assert question_text == "How do you manage risk?"
            assert tone == "formal"
            return fake_session

    class FakeDB:
        async def refresh(self, _obj) -> None:
            return None

    def fake_enqueue(*, thread_id: str, question_text: str, tone: str, session_id: str | None) -> str:
        enqueue_calls.append(
            {
                "thread_id": thread_id,
                "question_text": question_text,
                "tone": tone,
                "session_id": session_id,
            }
        )
        return "task-1"

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(ask_route, "workflow_event_bus", event_bus)
    monkeypatch.setattr(ask_route, "enqueue_ask_workflow", fake_enqueue)

    payload = AskRequest(question_text="How do you manage risk?", tone="formal", thread_id=thread_id)
    response = asyncio.run(ask_route.ask_question(payload=payload, db=FakeDB()))

    assert response.session.id == fake_session.id
    assert enqueue_calls
    assert enqueue_calls[0]["thread_id"] == thread_id
    assert enqueue_calls[0]["session_id"] == str(fake_session.id)
    assert event_bus.registered == [(thread_id, str(fake_session.id))]
    assert event_bus.thread_events[0]["reason"] == "workflow_queued"
    assert event_bus.session_events[0]["reason"] == "workflow_queued"


def test_ask_route_returns_503_when_enqueue_fails(monkeypatch) -> None:
    thread_id = "thread-456"
    fake_session = _build_session(thread_id)
    event_bus = _FakeWorkflowEventBus()

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def create_or_get_session(self, *, thread_id: str, question_text: str, tone: str):
            return fake_session

    class FakeDB:
        async def refresh(self, _obj) -> None:
            return None

    def fake_enqueue(*, thread_id: str, question_text: str, tone: str, session_id: str | None) -> str:
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(ask_route, "workflow_event_bus", event_bus)
    monkeypatch.setattr(ask_route, "enqueue_ask_workflow", fake_enqueue)

    payload = AskRequest(question_text="How do you manage risk?", tone="formal", thread_id=thread_id)
    try:
        asyncio.run(ask_route.ask_question(payload=payload, db=FakeDB()))
        raise AssertionError("Expected HTTPException when enqueue fails")
    except HTTPException as exc:
        assert exc.status_code == 503
