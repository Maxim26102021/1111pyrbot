from __future__ import annotations

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import Sequence, Tuple

from celery import Task

from libs.core.logging import json_log

from .celery_app import celery_app, settings
from .dao import (
    get_active_users,
    get_recent_summaries,
    get_user_channels,
    insert_digest,
)
from .utils import format_digest

logger = logging.getLogger(__name__)
SERVICE = "scheduler"

METRICS = {
    "runs_total": 0,
    "digests_created": 0,
    "users_skipped": 0,
}


async def _build_and_dispatch(now: datetime) -> None:
    since = now - settings.lookback_timedelta
    users = await get_active_users(settings.database_url)

    for user_id, tg_user_id, lang in users:
        channels = await get_user_channels(settings.database_url, user_id)
        if not channels:
            continue

        summaries = await get_recent_summaries(settings.database_url, channels, since)
        if not summaries:
            continue

        digest_text = format_digest(summaries)
        if not digest_text:
            METRICS["users_skipped"] += 1
            json_log(logger, "info", "digest_skipped_empty", service=SERVICE, user_id=user_id)
            continue

        digest_id = await insert_digest(
            settings.database_url,
            user_id=user_id,
            slot=now.isoformat(),
            summaries=summaries,
        )

        celery_app.send_task(
            "send_digest",
            args=[user_id, digest_text],
            queue=settings.queue_bot,
        )

        METRICS["digests_created"] += 1
        json_log(
            logger,
            "info",
            "digest_enqueued",
            service=SERVICE,
            user_id=user_id,
            digest_id=digest_id,
            summaries_count=len(summaries),
        )


@celery_app.task(
    name="build_and_dispatch_digest",
    bind=True,
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    retry_kwargs={"max_retries": 3},
)
def build_and_dispatch_digest(self: Task) -> None:
    start = time.perf_counter()
    now = datetime.now(timezone.utc)
    try:
        METRICS["runs_total"] += 1
        asyncio.run(_build_and_dispatch(now))
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        json_log(logger, "info", "digest_job_finished", service=SERVICE, latency_ms=latency_ms)
