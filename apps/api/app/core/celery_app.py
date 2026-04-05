"""Celery application wiring."""

from __future__ import annotations

from celery import Celery

from app.core.config import settings

celery_app = Celery(
    "respondai",
    broker=settings.app_celery_broker_url,
    backend=settings.app_celery_result_backend,
    include=["app.tasks.workflows"],
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
)
