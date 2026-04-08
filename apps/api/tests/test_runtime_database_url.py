import asyncio

from app.core.config import Settings
from app.graph import runtime


def test_checkpointer_conn_string_derives_from_database_url(monkeypatch) -> None:
    monkeypatch.setattr(
        runtime,
        "settings",
        Settings(
            _env_file=None,
            database_url="postgresql+psycopg://user:pass@db:5432/respondai",
        ),
    )

    assert runtime._checkpointer_conn_string() == "postgresql://user:pass@db:5432/respondai"


def test_ensure_checkpointer_ready_runs_setup_once(monkeypatch) -> None:
    setup_calls = 0

    class _FakeCheckpointer:
        async def setup(self) -> None:
            nonlocal setup_calls
            setup_calls += 1

    class _FakeSaver:
        @classmethod
        def from_conn_string(cls, _conn_string: str):
            class _Ctx:
                async def __aenter__(self) -> _FakeCheckpointer:
                    return _FakeCheckpointer()

                async def __aexit__(self, exc_type, exc, tb) -> None:
                    return None

            return _Ctx()

    runtime._CHECKPOINTER_READY = False
    runtime._CHECKPOINTER_SETUP_LOCK = asyncio.Lock()
    monkeypatch.setattr(runtime, "AsyncPostgresSaver", _FakeSaver)

    async def _run() -> None:
        await runtime.ensure_checkpointer_ready()
        await runtime.ensure_checkpointer_ready()

    asyncio.run(_run())

    assert setup_calls == 1
