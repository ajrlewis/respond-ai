"""Health endpoints."""

import logging

from fastapi import APIRouter

from app.services.workflow_events import workflow_event_bus

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
async def health() -> dict:
    """Liveness endpoint with Redis dependency signal."""

    logger.debug("Health check requested")
    redis_ok = await workflow_event_bus.is_healthy()
    return {
        "status": "ok" if redis_ok else "degraded",
        "redis": "ok" if redis_ok else "error",
    }
