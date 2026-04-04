"""FastAPI entrypoint."""

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware

from app.ai.factory import validate_ai_configuration
from app.core.config import settings
from app.core.logging import configure_logging
from app.db.migrations_or_init import init_database_async
from app.routes.ask import router as ask_router
from app.routes.auth import router as auth_router
from app.routes.documents import router as documents_router
from app.routes.evals import router as evals_router
from app.routes.health import router as health_router
from app.routes.review import router as review_router

configure_logging()
logger = logging.getLogger(__name__)


def _allowed_web_origins() -> list[str]:
    origins = [item.strip() for item in settings.app_web_origin.split(",") if item.strip()]
    return origins or ["http://localhost:3000"]


def create_app(*, register_startup: bool = True) -> FastAPI:
    """Create FastAPI app instance with middleware, routes, and optional startup hooks."""

    application = FastAPI(title=settings.app_name)
    application.add_middleware(
        SessionMiddleware,
        secret_key=settings.app_session_secret,
        same_site="lax",
        https_only=settings.app_env.lower() == "production",
    )
    application.add_middleware(
        CORSMiddleware,
        allow_origins=_allowed_web_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    if register_startup:

        @application.on_event("startup")
        async def on_startup() -> None:
            """Bootstrap database schema for local MVP."""

            logger.info("API startup initialization started")
            validate_ai_configuration()
            await init_database_async()
            logger.info("API startup initialization completed")

    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(ask_router)
    application.include_router(review_router)
    application.include_router(documents_router)
    application.include_router(evals_router)
    return application


app = create_app()
