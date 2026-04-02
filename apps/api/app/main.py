"""FastAPI entrypoint."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.ai.factory import validate_ai_configuration
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.migrations_or_init import init_database_async
from app.routes.ask import router as ask_router
from app.routes.documents import router as documents_router
from app.routes.evals import router as evals_router
from app.routes.health import router as health_router
from app.routes.review import router as review_router

configure_logging()
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.app_name)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup() -> None:
    """Bootstrap database schema for local MVP."""

    logger.info("API startup initialization started")
    validate_ai_configuration()
    await init_database_async()
    logger.info("API startup initialization completed")


app.include_router(health_router)
app.include_router(ask_router)
app.include_router(review_router)
app.include_router(documents_router)
app.include_router(evals_router)
