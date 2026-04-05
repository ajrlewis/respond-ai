import asyncio
from contextlib import asynccontextmanager
import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

from app.routes import ask as ask_route
from app.schemas.sessions import ConfidenceOut, SessionOut
from app.services.workflow_events import WorkflowEvent


class _FakeRequest:
    def __init__(self) -> None:
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


class _FakeSubscription:
    def __init__(self) -> None:
        self.queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue(maxsize=16)

    async def next_event(self, timeout: float) -> WorkflowEvent | None:
        try:
            return await asyncio.wait_for(self.queue.get(), timeout=timeout)
        except TimeoutError:
            return None


class _FakeWorkflowEventBus:
    def __init__(self) -> None:
        self._session_subscribers: dict[str, list[_FakeSubscription]] = {}

    @asynccontextmanager
    async def subscribe_session(self, session_id: str):
        sub = _FakeSubscription()
        self._session_subscribers.setdefault(session_id, []).append(sub)
        try:
            yield sub
        finally:
            subscribers = self._session_subscribers.get(session_id, [])
            if sub in subscribers:
                subscribers.remove(sub)
            if not subscribers:
                self._session_subscribers.pop(session_id, None)

    async def publish_session(
        self,
        *,
        session_id: str | None,
        reason: str,
        node_name: str | None = None,
        status: str | None = None,
        error: str | None = None,
        event: str = "workflow_state",
        thread_id: str | None = None,
    ) -> None:
        if not session_id:
            return
        signal = WorkflowEvent(
            reason=reason,
            event=event,
            node_name=node_name,
            status=status,
            error=error,
        )
        for subscriber in self._session_subscribers.get(session_id, []):
            await subscriber.queue.put(signal)

    async def session_subscriber_count(self, session_id: str) -> int:
        return len(self._session_subscribers.get(session_id, []))


def _decode_sse_frame(frame: bytes | str) -> tuple[str, dict]:
    raw = frame.decode("utf-8") if isinstance(frame, bytes) else frame
    lines = [line for line in raw.splitlines() if line]
    event_line = next(line for line in lines if line.startswith("event: "))
    data_lines = [line[len("data: ") :] for line in lines if line.startswith("data: ")]
    return event_line.removeprefix("event: "), json.loads("\n".join(data_lines))


def _session_snapshot(*, session_id: UUID, status: str, current_node: str) -> SessionOut:
    now = datetime.now(UTC)
    return SessionOut(
        id=session_id,
        question_text="How do you manage concentration risk?",
        question_type="risk",
        tone="formal",
        status=status,
        current_node=current_node,
        draft_answer="Draft answer",
        final_answer=None,
        confidence_notes="ok",
        confidence=ConfidenceOut(),
        created_at=now,
        updated_at=now,
    )


def test_session_sse_emits_initial_snapshot_and_updates(monkeypatch) -> None:
    session_id = uuid4()
    bus = _FakeWorkflowEventBus()
    snapshots = [
        _session_snapshot(session_id=session_id, status="draft", current_node="ask"),
        _session_snapshot(session_id=session_id, status="awaiting_review", current_node="draft_response"),
    ]
    load_calls = 0

    class FakeSessionService:
        def __init__(self, db) -> None:
            self.db = db

        async def get_session(self, incoming_session_id):
            assert incoming_session_id == session_id
            return object()

    async def fake_load(_session_id):
        nonlocal load_calls
        load_calls += 1
        return snapshots[min(load_calls - 1, len(snapshots) - 1)]

    monkeypatch.setattr(ask_route, "workflow_event_bus", bus)
    monkeypatch.setattr(ask_route, "SessionService", FakeSessionService)
    monkeypatch.setattr(ask_route, "_load_session_schema_by_id", fake_load)

    async def _run() -> tuple[str, dict, str, dict, int]:
        request = _FakeRequest()
        response = await ask_route.stream_session_events(
            session_id=session_id,
            request=request,
            db=object(),
        )
        iterator = response.body_iterator.__aiter__()

        first_frame = await asyncio.wait_for(iterator.__anext__(), timeout=1.0)
        await bus.publish_session(
            session_id=str(session_id),
            reason="node_completed",
            node_name="draft_response",
            status="awaiting_review",
        )
        second_frame = await asyncio.wait_for(iterator.__anext__(), timeout=1.0)

        request.disconnected = True
        try:
            await asyncio.wait_for(iterator.__anext__(), timeout=1.0)
        except StopAsyncIteration:
            pass

        return (
            *_decode_sse_frame(first_frame),
            *_decode_sse_frame(second_frame),
            await bus.session_subscriber_count(str(session_id)),
        )

    first_event, first_payload, second_event, second_payload, subscriber_count = asyncio.run(_run())

    assert first_event == "workflow_state"
    assert first_payload["reason"] == "snapshot"
    assert first_payload["session"]["id"] == str(session_id)
    assert first_payload["session"]["current_node"] == "ask"

    assert second_event == "workflow_state"
    assert second_payload["reason"] == "node_completed"
    assert second_payload["node"] == "draft_response"
    assert second_payload["status"] == "awaiting_review"
    assert second_payload["session"]["status"] == "awaiting_review"
    assert subscriber_count == 0
