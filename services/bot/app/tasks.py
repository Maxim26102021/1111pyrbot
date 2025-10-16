from __future__ import annotations

import asyncio
import logging

from celery import Task

from .celery_app import celery_app, settings
from .messaging import send_text, RetryableTelegramError, FatalTelegramError, METRICS as BOT_METRICS
from libs.core.logging import json_log

logger = logging.getLogger(__name__)
SERVICE = "bot-worker"


@celery_app.task(
    name="send_digest",
    bind=True,
    autoretry_for=(RetryableTelegramError, TimeoutError, ConnectionError),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 6},
)
def send_digest(self: Task, tg_user_id: int, text: str, parse_mode: str | None = None) -> None:
    try:
        chunks = asyncio.run(send_text(tg_user_id, text, parse_mode=parse_mode))
    except FatalTelegramError as exc:
        json_log(logger, "warning", "digest_delivery_failed", service=SERVICE, user_id=tg_user_id, error=str(exc))
        return

    json_log(
        logger,
        "info",
        "digest_delivered",
        service=SERVICE,
        user_id=tg_user_id,
        chunks=chunks,
        retries=self.request.retries,
        messages_sent=BOT_METRICS["messages_sent"],
    )
