"""Redis-backed workflow event distribution for SSE streams."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from contextlib import asynccontextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from typing import Any, AsyncIterator

from app.services.redis_client import close_redis_client, get_redis_client, ping_redis

logger = logging.getLogger(__name__)

_THREAD_SESSION_TTL_SECONDS = 24 * 60 * 60


@dataclass(slots=True, frozen=True)
class WorkflowEvent:
    """Signal emitted for workflow updates."""

    reason: str
    event: str = "workflow_state"
    node_name: str | None = None
    status: str | None = None
    error: str | None = None
    metadata: dict[str, Any] | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class RedisWorkflowSubscription:
    """Per-connection Redis pub/sub reader."""

    def __init__(self, *, bus: "WorkflowEventBus", channels: list[str]) -> None:
        self._bus = bus
        self._channels = channels
        self._pubsub = None
        self._closed = False

    async def __aenter__(self) -> "RedisWorkflowSubscription":
        redis_client = get_redis_client()
        self._pubsub = redis_client.pubsub()
        await self._pubsub.subscribe(*self._channels)
        await self._bus._increment_subscribers(self._channels)
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        await self.close()

    async def next_event(self, timeout: float) -> WorkflowEvent | None:
        """Return next decoded workflow event, or `None` on timeout."""

        if self._closed or self._pubsub is None:
            return None

        message = await self._pubsub.get_message(ignore_subscribe_messages=True, timeout=timeout)
        if not message:
            return None
        return self._bus._decode_message(message)

    async def close(self) -> None:
        if self._closed:
            return
        self._closed = True
        if self._pubsub is not None:
            await self._pubsub.unsubscribe(*self._channels)
            await self._pubsub.aclose()
        await self._bus._decrement_subscribers(self._channels)


class WorkflowEventBus:
    """Redis pub/sub workflow event fanout keyed by session/thread ids."""

    def __init__(self, *, channel_prefix: str = "workflow") -> None:
        self._channel_prefix = channel_prefix.rstrip(":")
        self._subscriber_counts: dict[str, int] = defaultdict(int)
        self._subscriber_lock = asyncio.Lock()

    def _session_channel(self, session_id: str) -> str:
        return f"{self._channel_prefix}:session:{session_id}"

    def _thread_channel(self, thread_id: str) -> str:
        return f"{self._channel_prefix}:thread:{thread_id}"

    def _document_channel(self, document_id: str) -> str:
        return f"{self._channel_prefix}:document:{document_id}"

    def _thread_session_key(self, thread_id: str) -> str:
        return f"{self._channel_prefix}:thread_session:{thread_id}"

    def _session_threads_key(self, session_id: str) -> str:
        return f"{self._channel_prefix}:session_threads:{session_id}"

    @staticmethod
    def _serialize_event(signal: WorkflowEvent) -> str:
        return json.dumps(
            {
                "reason": signal.reason,
                "event": signal.event,
                "node_name": signal.node_name,
                "status": signal.status,
                "error": signal.error,
                "metadata": signal.metadata,
                "timestamp": signal.timestamp,
            },
            separators=(",", ":"),
            ensure_ascii=False,
        )

    @staticmethod
    def _decode_message(message: dict[str, Any]) -> WorkflowEvent | None:
        raw_data = message.get("data")
        if isinstance(raw_data, bytes):
            raw_data = raw_data.decode("utf-8")
        if not isinstance(raw_data, str):
            return None

        try:
            payload = json.loads(raw_data)
        except json.JSONDecodeError:
            logger.warning("Ignoring malformed workflow event payload: %s", raw_data)
            return None

        if not isinstance(payload, dict):
            return None

        return WorkflowEvent(
            reason=str(payload.get("reason", "")),
            event=str(payload.get("event", "workflow_state")),
            node_name=str(payload.get("node_name")) if payload.get("node_name") is not None else None,
            status=str(payload.get("status")) if payload.get("status") is not None else None,
            error=str(payload.get("error")) if payload.get("error") is not None else None,
            metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
            timestamp=str(payload.get("timestamp") or datetime.now(UTC).isoformat()),
        )

    async def _increment_subscribers(self, channels: list[str]) -> None:
        async with self._subscriber_lock:
            for channel in channels:
                self._subscriber_counts[channel] += 1

    async def _decrement_subscribers(self, channels: list[str]) -> None:
        async with self._subscriber_lock:
            for channel in channels:
                next_count = self._subscriber_counts.get(channel, 0) - 1
                if next_count <= 0:
                    self._subscriber_counts.pop(channel, None)
                else:
                    self._subscriber_counts[channel] = next_count

    @asynccontextmanager
    async def subscribe_session(self, session_id: str) -> AsyncIterator[RedisWorkflowSubscription]:
        """Create a Redis pub/sub subscription for a session channel."""

        subscription = RedisWorkflowSubscription(bus=self, channels=[self._session_channel(session_id)])
        await subscription.__aenter__()
        try:
            yield subscription
        finally:
            await subscription.close()

    @asynccontextmanager
    async def subscribe_thread(self, thread_id: str) -> AsyncIterator[RedisWorkflowSubscription]:
        """Create a Redis pub/sub subscription for a thread channel."""

        subscription = RedisWorkflowSubscription(bus=self, channels=[self._thread_channel(thread_id)])
        await subscription.__aenter__()
        try:
            yield subscription
        finally:
            await subscription.close()

    @asynccontextmanager
    async def subscribe_document(self, document_id: str) -> AsyncIterator[RedisWorkflowSubscription]:
        """Create a Redis pub/sub subscription for a response-document channel."""

        subscription = RedisWorkflowSubscription(bus=self, channels=[self._document_channel(document_id)])
        await subscription.__aenter__()
        try:
            yield subscription
        finally:
            await subscription.close()

    async def register_thread_session(self, *, thread_id: str, session_id: str) -> None:
        """Record thread-to-session mapping for cross-channel fanout."""

        if not thread_id or not session_id:
            return
        try:
            redis_client = get_redis_client()
            await redis_client.set(self._thread_session_key(thread_id), session_id, ex=_THREAD_SESSION_TTL_SECONDS)
            session_threads_key = self._session_threads_key(session_id)
            await redis_client.sadd(session_threads_key, thread_id)
            await redis_client.expire(session_threads_key, _THREAD_SESSION_TTL_SECONDS)
        except Exception as exc:  # pragma: no cover - defensive transport safety
            logger.warning("Failed to register workflow thread/session mapping: %s", exc)

    async def publish_session(
        self,
        *,
        session_id: str | None,
        reason: str,
        node_name: str | None = None,
        status: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        event: str = "workflow_state",
        thread_id: str | None = None,
    ) -> None:
        """Publish event to session channel and mapped thread channels."""

        if not session_id:
            return

        try:
            redis_client = get_redis_client()
            signal = WorkflowEvent(
                reason=reason,
                event=event,
                node_name=node_name,
                status=status,
                error=error,
                metadata=metadata,
            )
            payload = self._serialize_event(signal)

            channels = {self._session_channel(session_id)}
            threads = await redis_client.smembers(self._session_threads_key(session_id))
            if thread_id:
                threads.add(thread_id)
            channels.update(self._thread_channel(item) for item in threads if item)

            for channel in channels:
                await redis_client.publish(channel, payload)
        except Exception as exc:  # pragma: no cover - defensive transport safety
            logger.warning("Failed to publish session workflow event session_id=%s: %s", session_id, exc)

    async def publish_thread(
        self,
        *,
        thread_id: str,
        reason: str,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        event: str = "workflow_state",
    ) -> None:
        """Publish event to thread channel and mapped session channel."""

        try:
            signal = WorkflowEvent(
                reason=reason,
                event=event,
                error=error,
                metadata=metadata,
            )
            payload = self._serialize_event(signal)

            redis_client = get_redis_client()
            channels = {self._thread_channel(thread_id)}
            mapped_session = await redis_client.get(self._thread_session_key(thread_id))
            if mapped_session:
                channels.add(self._session_channel(mapped_session))

            for channel in channels:
                await redis_client.publish(channel, payload)
        except Exception as exc:  # pragma: no cover - defensive transport safety
            logger.warning("Failed to publish thread workflow event thread_id=%s: %s", thread_id, exc)

    async def publish_document(
        self,
        *,
        document_id: str,
        reason: str,
        node_name: str | None = None,
        status: str | None = None,
        error: str | None = None,
        metadata: dict[str, Any] | None = None,
        event: str = "workflow_state",
    ) -> None:
        """Publish event to response-document channel."""

        try:
            signal = WorkflowEvent(
                reason=reason,
                event=event,
                node_name=node_name,
                status=status,
                error=error,
                metadata=metadata,
            )
            payload = self._serialize_event(signal)

            redis_client = get_redis_client()
            await redis_client.publish(self._document_channel(document_id), payload)
        except Exception as exc:  # pragma: no cover - defensive transport safety
            logger.warning("Failed to publish document workflow event document_id=%s: %s", document_id, exc)

    async def session_subscriber_count(self, session_id: str) -> int:
        """Return local process subscriber count for a session channel."""

        async with self._subscriber_lock:
            return self._subscriber_counts.get(self._session_channel(session_id), 0)

    async def is_healthy(self) -> bool:
        """Return whether Redis is reachable for workflow event distribution."""

        return await ping_redis()

    async def close(self) -> None:
        """Close shared Redis resources."""

        await close_redis_client()


def format_sse_event(*, event: str, data: dict[str, Any]) -> str:
    """Serialize an SSE event payload."""

    body = json.dumps(data, separators=(",", ":"), ensure_ascii=False)
    lines = [f"event: {event}"]
    for line in body.splitlines() or ["{}"]:
        lines.append(f"data: {line}")
    return "\n".join(lines) + "\n\n"


def format_sse_comment(comment: str = "keepalive") -> str:
    """Serialize an SSE comment frame."""

    return f": {comment}\n\n"


workflow_event_bus = WorkflowEventBus()
