"""Logging configuration."""

import logging

from app.core.config import settings


def _resolve_level(level_name: str) -> int:
    """Resolve a textual log level to a logging constant."""

    normalized_level = level_name.strip().upper()
    return logging.getLevelNamesMapping().get(normalized_level, logging.INFO)


def configure_logging() -> None:
    """Configure root logging once for the application."""

    logging.basicConfig(
        level=_resolve_level(settings.logging_level),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
    )
