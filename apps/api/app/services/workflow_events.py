"""In-memory workflow event broadcasting for SSE streams."""

from __future__ import annotations

import asyncio
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime
import json
import logging
from typing import Any

logger = logging.getLogger(__name__)


@dataclass(slots=True, frozen=True)
class WorkflowEvent:
    """Signal emitted for workflow updates."""

    reason: str
    event: str = "workflow_state"
    node_name: str | None = None
    status: str | None = None
    error: str | None = None
    timestamp: str = field(default_factory=lambda: datetime.now(UTC).isoformat())


class WorkflowEventBus:
    """Lightweight in-memory pub/sub keyed by workflow session/thread ids."""

    def __init__(self) -> None:
        self._session_subscribers: dict[str, set[asyncio.Queue[WorkflowEvent]]] = defaultdict(set)
        self._thread_subscribers: dict[str, set[asyncio.Queue[WorkflowEvent]]] = defaultdict(set)
        self._thread_to_session: dict[str, str] = {}
        self._session_to_threads: dict[str, set[str]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe_session(self, session_id: str) -> asyncio.Queue[WorkflowEvent]:
        """Create a queue subscription for a session id."""

        queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._session_subscribers[session_id].add(queue)
        return queue

    async def subscribe_thread(self, thread_id: str) -> asyncio.Queue[WorkflowEvent]:
        """Create a queue subscription for a graph thread id."""

        queue: asyncio.Queue[WorkflowEvent] = asyncio.Queue(maxsize=64)
        async with self._lock:
            self._thread_subscribers[thread_id].add(queue)
        return queue

    async def unsubscribe_session(self, session_id: str, queue: asyncio.Queue[WorkflowEvent]) -> None:
        """Remove a session queue subscription."""

        async with self._lock:
            subscribers = self._session_subscribers.get(session_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._session_subscribers.pop(session_id, None)

    async def unsubscribe_thread(self, thread_id: str, queue: asyncio.Queue[WorkflowEvent]) -> None:
        """Remove a thread queue subscription."""

        async with self._lock:
            subscribers = self._thread_subscribers.get(thread_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._thread_subscribers.pop(thread_id, None)

    async def register_thread_session(self, *, thread_id: str, session_id: str) -> None:
        """Record thread-to-session mapping for fanout."""

        async with self._lock:
            self._thread_to_session[thread_id] = session_id
            self._session_to_threads[session_id].add(thread_id)

    async def publish_session(
        self,
        *,
        session_id: str | None,
        reason: str,
        node_name: str | None = None,
        status: str | None = None,
        error: str | None = None,
        event: str = "workflow_state",
    ) -> None:
        """Broadcast an event to all subscribers for a session (and mapped thread)."""

        if not session_id:
            return

        signal = WorkflowEvent(
            event=event,
            reason=reason,
            node_name=node_name,
            status=status,
            error=error,
        )

        async with self._lock:
            subscribers = list(self._session_subscribers.get(session_id, set()))
            for thread_id in self._session_to_threads.get(session_id, set()):
                subscribers.extend(self._thread_subscribers.get(thread_id, set()))

        for queue in subscribers:
            self._enqueue(queue, signal)

    async def publish_thread(
        self,
        *,
        thread_id: str,
        reason: str,
        error: str | None = None,
        event: str = "workflow_state",
    ) -> None:
        """Broadcast an event directly to thread subscribers."""

        signal = WorkflowEvent(event=event, reason=reason, error=error)
        async with self._lock:
            subscribers = list(self._thread_subscribers.get(thread_id, set()))
            mapped_session = self._thread_to_session.get(thread_id)
            if mapped_session:
                subscribers.extend(self._session_subscribers.get(mapped_session, set()))

        for queue in subscribers:
            self._enqueue(queue, signal)

    async def session_subscriber_count(self, session_id: str) -> int:
        """Return active session subscriber count for tests/debugging."""

        async with self._lock:
            return len(self._session_subscribers.get(session_id, set()))

    @staticmethod
    def _enqueue(queue: asyncio.Queue[WorkflowEvent], signal: WorkflowEvent) -> None:
        if queue.full():
            try:
                queue.get_nowait()
            except asyncio.QueueEmpty:
                pass

        try:
            queue.put_nowait(signal)
        except asyncio.QueueFull:
            logger.debug("Dropping workflow event because subscriber queue is full.")


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
