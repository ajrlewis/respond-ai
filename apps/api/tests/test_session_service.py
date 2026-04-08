import asyncio
from types import SimpleNamespace

from app.services.session_service import SessionService


def test_get_session_by_thread_id_uses_populate_existing() -> None:
    captured: dict[str, object] = {}
    sentinel = SimpleNamespace()

    class _Result:
        def scalar_one_or_none(self):
            return sentinel

    class _DB:
        async def execute(self, stmt):
            captured["stmt"] = stmt
            return _Result()

        async def refresh(self, obj):
            captured["refreshed"] = obj

    service = SessionService(_DB())
    result = asyncio.run(service.get_session_by_thread_id("thread-123"))

    assert result is sentinel
    statement = captured["stmt"]
    assert statement._execution_options.get("populate_existing") is True
    assert captured["refreshed"] is sentinel
