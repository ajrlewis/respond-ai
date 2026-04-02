"""Health endpoints."""

import logging

from fastapi import APIRouter

router = APIRouter(tags=["health"])
logger = logging.getLogger(__name__)


@router.get("/health")
def health() -> dict:
    """Simple liveness endpoint."""

    logger.debug("Health check requested")
    return {"status": "ok"}
