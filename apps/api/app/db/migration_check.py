"""Schema version checks backed by Alembic revision state."""

from __future__ import annotations

from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import async_engine, engine

_MIGRATION_HINT = "Run `cd apps/api && uv run alembic upgrade head` before starting the API."


def _api_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _alembic_config() -> Config:
    api_root = _api_root()
    config = Config(str(api_root / "alembic.ini"))
    config.set_main_option("script_location", str(api_root / "alembic"))
    return config


def _expected_heads() -> set[str]:
    script = ScriptDirectory.from_config(_alembic_config())
    return set(script.get_heads())


def _assert_heads_match(current_heads: set[str]) -> None:
    expected_heads = _expected_heads()
    if not current_heads:
        raise RuntimeError(f"Database schema has no Alembic revision. {_MIGRATION_HINT}")
    if current_heads != expected_heads:
        raise RuntimeError(
            "Database schema revision does not match application migrations. "
            f"current={sorted(current_heads)} expected={sorted(expected_heads)}. {_MIGRATION_HINT}"
        )


async def assert_schema_current_async() -> None:
    """Raise when connected database is missing or behind Alembic migrations."""

    try:
        async with async_engine.connect() as connection:
            result = await connection.execute(text("SELECT version_num FROM alembic_version"))
            current_heads = {str(row[0]) for row in result if row and row[0]}
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database schema migration check failed. {_MIGRATION_HINT}") from exc
    _assert_heads_match(current_heads)


def assert_schema_current_sync() -> None:
    """Sync variant for scripts that use the sync SQLAlchemy engine."""

    try:
        with engine.connect() as connection:
            result = connection.execute(text("SELECT version_num FROM alembic_version"))
            current_heads = {str(row[0]) for row in result if row and row[0]}
    except SQLAlchemyError as exc:
        raise RuntimeError(f"Database schema migration check failed. {_MIGRATION_HINT}") from exc
    _assert_heads_match(current_heads)
