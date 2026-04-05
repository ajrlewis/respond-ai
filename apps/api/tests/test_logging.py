import logging
from unittest.mock import patch

from app.core.config import Settings
from app.core.logging import _resolve_level, configure_logging


def test_resolve_level_is_case_insensitive() -> None:
    assert _resolve_level("debug") == logging.DEBUG
    assert _resolve_level("Info") == logging.INFO


def test_resolve_level_falls_back_to_info_for_unknown_values() -> None:
    assert _resolve_level("not-a-real-level") == logging.INFO


def test_configure_logging_uses_settings_logging_level(monkeypatch) -> None:
    monkeypatch.setattr("app.core.logging.settings", Settings(_env_file=None, logging_level="DEBUG"))

    with patch("app.core.logging.logging.basicConfig") as mock_basic_config:
        configure_logging()

    assert mock_basic_config.called
    assert mock_basic_config.call_args.kwargs["level"] == logging.DEBUG
