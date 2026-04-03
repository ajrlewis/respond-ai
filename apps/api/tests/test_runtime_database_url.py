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
