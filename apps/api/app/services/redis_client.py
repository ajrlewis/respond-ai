"""Shared Redis client helpers."""

from __future__ import annotations

import logging

from redis.asyncio import Redis
from redis.asyncio import from_url as redis_from_url

from app.core.config import settings

logger = logging.getLogger(__name__)

_redis_client: Redis | None = None


def get_redis_client() -> Redis:
    """Return a process-local async Redis client."""

    global _redis_client
    if _redis_client is None:
        _redis_client = redis_from_url(settings.app_redis_url, decode_responses=True)
    return _redis_client


async def close_redis_client() -> None:
    """Close and clear the process-local Redis client."""

    global _redis_client
    if _redis_client is None:
        return
    await _redis_client.aclose()
    _redis_client = None


async def ping_redis() -> bool:
    """Return whether Redis is reachable."""

    try:
        client = get_redis_client()
        result = await client.ping()
        return bool(result)
    except Exception as exc:  # pragma: no cover - defensive connectivity logging
        logger.warning("Redis ping failed: %s", exc)
        return False
