from __future__ import annotations

import logging
from datetime import timedelta

from celery import Celery
from celery.schedules import schedule
from kombu import Queue

from .config import load_settings
from .utils import add_jitter

settings = load_settings()

logger = logging.getLogger(__name__)

celery_app = Celery(
    "digest_scheduler",
    broker=settings.broker,
    backend=settings.backend,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_default_queue=settings.queue_digest,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_queues=(
        Queue(settings.queue_digest),
        Queue(settings.queue_bot),
    ),
)


def _schedule_with_jitter() -> schedule:
    base = settings.period_timedelta
    jittered = add_jitter(base, settings.digest_jitter_seconds)
    return schedule(run_every=jittered)


celery_app.conf.beat_schedule = {
    "build-and-dispatch": {
        "task": "build_and_dispatch_digest",
        "schedule": _schedule_with_jitter(),
    }
}


logger.info(
    "Scheduler configured",
    extra={
        "queue_digest": settings.queue_digest,
        "queue_bot": settings.queue_bot,
        "period_minutes": settings.digest_period_minutes,
    },
)
