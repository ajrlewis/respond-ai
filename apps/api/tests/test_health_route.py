import asyncio

from app.routes import health as health_route


def test_health_reports_ok_when_redis_healthy(monkeypatch) -> None:
    class FakeBus:
        async def is_healthy(self) -> bool:
            return True

    monkeypatch.setattr(health_route, "workflow_event_bus", FakeBus())
    payload = asyncio.run(health_route.health())
    assert payload == {"status": "ok", "redis": "ok"}


def test_health_reports_degraded_when_redis_unhealthy(monkeypatch) -> None:
    class FakeBus:
        async def is_healthy(self) -> bool:
            return False

    monkeypatch.setattr(health_route, "workflow_event_bus", FakeBus())
    payload = asyncio.run(health_route.health())
    assert payload == {"status": "degraded", "redis": "error"}
