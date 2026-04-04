import asyncio

from app.tasks import workflows


class _FakeWorkflowEventBus:
    def __init__(self) -> None:
        self.session_events: list[dict] = []
        self.thread_events: list[dict] = []
        self.mappings: list[tuple[str, str]] = []

    async def publish_session(self, **kwargs) -> None:
        self.session_events.append(kwargs)

    async def publish_thread(self, **kwargs) -> None:
        self.thread_events.append(kwargs)

    async def register_thread_session(self, *, thread_id: str, session_id: str) -> None:
        self.mappings.append((thread_id, session_id))


def test_run_ask_workflow_async_invokes_runtime(monkeypatch) -> None:
    calls: list[dict] = []
    event_bus = _FakeWorkflowEventBus()

    async def fake_run_until_human_review(payload: dict, thread_id: str) -> dict:
        calls.append({"payload": payload, "thread_id": thread_id})
        return {"session_id": "session-1", "status": "awaiting_review"}

    monkeypatch.setattr(workflows, "workflow_event_bus", event_bus)
    monkeypatch.setattr(workflows, "run_until_human_review", fake_run_until_human_review)

    asyncio.run(
        workflows._run_ask_workflow_async(
            thread_id="thread-1",
            question_text="How do you manage concentration risk?",
            tone="formal",
            session_id="session-1",
        )
    )

    assert calls
    assert calls[0]["thread_id"] == "thread-1"
    assert calls[0]["payload"]["question_text"] == "How do you manage concentration risk?"
    assert event_bus.thread_events[0]["reason"] == "workflow_started"
    assert any(event["reason"] == "workflow_paused_for_review" for event in event_bus.session_events)


def test_run_review_workflow_async_invokes_runtime(monkeypatch) -> None:
    calls: list[dict] = []
    event_bus = _FakeWorkflowEventBus()

    async def fake_resume_from_review(*, thread_id: str, review_payload: dict) -> dict:
        calls.append({"thread_id": thread_id, "review_payload": review_payload})
        return {"session_id": "session-2", "status": "approved"}

    monkeypatch.setattr(workflows, "workflow_event_bus", event_bus)
    monkeypatch.setattr(workflows, "resume_from_review", fake_resume_from_review)

    asyncio.run(
        workflows._run_review_workflow_async(
            thread_id="thread-2",
            review_payload={
                "session_id": "session-2",
                "reviewer_action": "approve",
                "review_comments": "",
            },
        )
    )

    assert calls
    assert calls[0]["thread_id"] == "thread-2"
    assert event_bus.session_events[0]["reason"] == "finalization_started"
    assert event_bus.session_events[-1]["reason"] == "workflow_completed"


def test_task_entrypoints_bridge_asyncio(monkeypatch) -> None:
    ask_calls: list[tuple[str, str, str, str | None]] = []
    review_calls: list[tuple[str, dict]] = []

    async def fake_run_ask(*, thread_id: str, question_text: str, tone: str, session_id: str | None) -> None:
        ask_calls.append((thread_id, question_text, tone, session_id))

    async def fake_run_review(*, thread_id: str, review_payload: dict) -> None:
        review_calls.append((thread_id, review_payload))

    monkeypatch.setattr(workflows, "_run_ask_workflow_async", fake_run_ask)
    monkeypatch.setattr(workflows, "_run_review_workflow_async", fake_run_review)

    workflows.run_ask_workflow_task(
        thread_id="thread-ask",
        question_text="How do you manage concentration risk?",
        tone="formal",
        session_id="session-ask",
    )
    workflows.run_review_workflow_task(
        thread_id="thread-review",
        review_payload={"session_id": "session-review", "reviewer_action": "revise"},
    )

    assert ask_calls == [("thread-ask", "How do you manage concentration risk?", "formal", "session-ask")]
    assert review_calls == [("thread-review", {"session_id": "session-review", "reviewer_action": "revise"})]
