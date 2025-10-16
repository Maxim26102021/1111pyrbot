from __future__ import annotations

import logging

from celery import Celery
from kombu import Queue

from .config import load_settings

settings = load_settings()

logger = logging.getLogger(__name__)

celery_app = Celery(
    "digest_bot",
    broker=settings.broker,
    backend=settings.backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_default_queue=settings.queue_bot,
    task_queues=(Queue(settings.queue_bot),),
)

logger.info("Celery bot app configured", extra={"queue": settings.queue_bot})
