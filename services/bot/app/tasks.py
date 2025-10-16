from __future__ import annotations

import asyncio
import logging

from celery import Task

from .celery_app import celery_app, settings
from .messaging import send_text, RetryableTelegramError, FatalTelegramError

logger = logging.getLogger(__name__)


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
        logger.warning(
            "Failed to deliver digest due to fatal error",
            extra={"user_id": tg_user_id, "error": str(exc)},
        )
        return

    logger.info(
        "Digest delivered",
        extra={
            "user_id": tg_user_id,
            "chunks": chunks,
            "retries": self.request.retries,
        },
    )
