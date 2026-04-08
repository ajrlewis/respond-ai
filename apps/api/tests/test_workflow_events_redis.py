from __future__ import annotations

import asyncio
from collections import defaultdict

from app.services import workflow_events


class _FakePubSub:
    def __init__(self, redis_client: "_FakeRedis") -> None:
        self._redis = redis_client
        self._channels: set[str] = set()
        self._queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=64)

    async def subscribe(self, *channels: str) -> None:
        for channel in channels:
            self._channels.add(channel)
            self._redis._subscribers[channel].append(self)

    async def unsubscribe(self, *channels: str) -> None:
        for channel in channels:
            if channel in self._channels:
                self._channels.remove(channel)
            if self in self._redis._subscribers.get(channel, []):
                self._redis._subscribers[channel].remove(self)

    async def get_message(self, ignore_subscribe_messages: bool = True, timeout: float = 0.0):
        try:
            return await asyncio.wait_for(self._queue.get(), timeout=timeout)
        except TimeoutError:
            return None

    async def aclose(self) -> None:
        await self.unsubscribe(*list(self._channels))


class _FakeRedis:
    def __init__(self) -> None:
        self._kv: dict[str, str] = {}
        self._sets: dict[str, set[str]] = defaultdict(set)
        self._subscribers: dict[str, list[_FakePubSub]] = defaultdict(list)

    def pubsub(self) -> _FakePubSub:
        return _FakePubSub(self)

    async def set(self, key: str, value: str, ex: int | None = None) -> None:
        self._kv[key] = value

    async def get(self, key: str) -> str | None:
        return self._kv.get(key)

    async def sadd(self, key: str, *values: str) -> None:
        self._sets[key].update(values)

    async def smembers(self, key: str) -> set[str]:
        return set(self._sets.get(key, set()))

    async def expire(self, key: str, ttl: int) -> None:
        return None

    async def publish(self, channel: str, message: str) -> None:
        for subscriber in list(self._subscribers.get(channel, [])):
            await subscriber._queue.put({"data": message})

    async def ping(self) -> bool:
        return True

    async def aclose(self) -> None:
        return None


def test_publish_session_fans_out_to_mapped_thread_subscribers(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(workflow_events, "get_redis_client", lambda: fake_redis)

    async def _run() -> tuple[str, str]:
        bus = workflow_events.WorkflowEventBus(channel_prefix="workflow")
        await bus.register_thread_session(thread_id="thread-1", session_id="session-1")
        async with bus.subscribe_thread("thread-1") as sub:
            await bus.publish_session(
                session_id="session-1",
                reason="node_completed",
                node_name="draft_response",
                status="awaiting_review",
            )
            signal = await sub.next_event(timeout=0.5)
            assert signal is not None
            return signal.reason, signal.node_name or ""

    reason, node_name = asyncio.run(_run())
    assert reason == "node_completed"
    assert node_name == "draft_response"


def test_publish_thread_reaches_mapped_session_subscribers(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(workflow_events, "get_redis_client", lambda: fake_redis)

    async def _run() -> tuple[str, str | None]:
        bus = workflow_events.WorkflowEventBus(channel_prefix="workflow")
        await bus.register_thread_session(thread_id="thread-2", session_id="session-2")
        async with bus.subscribe_session("session-2") as sub:
            await bus.publish_thread(thread_id="thread-2", reason="workflow_error", error="boom")
            signal = await sub.next_event(timeout=0.5)
            assert signal is not None
            return signal.reason, signal.error

    reason, error = asyncio.run(_run())
    assert reason == "workflow_error"
    assert error == "boom"


def test_publish_document_reaches_document_subscribers_with_metadata(monkeypatch) -> None:
    fake_redis = _FakeRedis()
    monkeypatch.setattr(workflow_events, "get_redis_client", lambda: fake_redis)

    async def _run() -> tuple[str, str | None, dict | None]:
        bus = workflow_events.WorkflowEventBus(channel_prefix="workflow")
        async with bus.subscribe_document("document-1") as sub:
            await bus.publish_document(
                document_id="document-1",
                reason="stage_update",
                node_name="rank_evidence",
                status="running",
                metadata={"run_id": "run-1", "operation": "generation"},
            )
            signal = await sub.next_event(timeout=0.5)
            assert signal is not None
            return signal.reason, signal.node_name, signal.metadata

    reason, node_name, metadata = asyncio.run(_run())
    assert reason == "stage_update"
    assert node_name == "rank_evidence"
    assert metadata == {"run_id": "run-1", "operation": "generation"}
