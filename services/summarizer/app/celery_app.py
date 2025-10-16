from __future__ import annotations

import logging

from celery import Celery
from kombu import Queue

from .config import load_settings

settings = load_settings()

celery_app = Celery(
    "digest",
    broker=settings.broker,
    backend=settings.backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_default_queue=settings.queue_summarize,
    task_routes={
        "summarize_post": {
            "queue": settings.queue_summarize,
        },
    },
    task_annotations={
        "*": {
            "retry_backoff": True,
            "retry_backoff_max": 60,
            "retry_jitter": True,
            "max_retries": 6,
        }
    },
    task_queues=(
        Queue(settings.queue_summarize),
        Queue(settings.queue_summarize_priority),
    ),
)

logging.getLogger(__name__).info(
    "Celery configured",
    extra={
        "broker": settings.broker,
        "backend": settings.backend,
        "queues": [settings.queue_summarize, settings.queue_summarize_priority],
    },
)
