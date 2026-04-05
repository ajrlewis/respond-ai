from pathlib import Path

import pytest

from app.db import migration_check


def test_alembic_config_points_to_repo_alembic_dir() -> None:
    config = migration_check._alembic_config()
    script_location = Path(config.get_main_option("script_location"))

    assert script_location.exists()
    assert script_location.name == "alembic"


def test_assert_heads_match_rejects_missing_revision(monkeypatch) -> None:
    monkeypatch.setattr(migration_check, "_expected_heads", lambda: {"head-1"})

    with pytest.raises(RuntimeError, match="no Alembic revision"):
        migration_check._assert_heads_match(set())


def test_assert_heads_match_rejects_mismatch(monkeypatch) -> None:
    monkeypatch.setattr(migration_check, "_expected_heads", lambda: {"head-1"})

    with pytest.raises(RuntimeError, match="does not match"):
        migration_check._assert_heads_match({"old-head"})


def test_assert_heads_match_accepts_expected_head(monkeypatch) -> None:
    monkeypatch.setattr(migration_check, "_expected_heads", lambda: {"head-1"})

    migration_check._assert_heads_match({"head-1"})
