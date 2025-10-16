from __future__ import annotations

import asyncio
import logging
import sys
from itertools import cycle
from pathlib import Path
from typing import Dict, Iterable, List, Sequence

from sqlalchemy import text
from sqlalchemy.exc import OperationalError
from telethon import events
from tenacity import AsyncRetrying, retry_if_exception_type, stop_after_attempt, wait_random_exponential

from libs.core.pg import session_scope

from .config import IngestSettings, load_settings
from .dao import get_or_create_channel, upsert_post
from .queue import TaskQueue, create_celery_app
from .telethon_client import TelethonShard

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 10_000
TRIMMING_SUFFIX = "\n\n…"


class MessageProcessor:
    def __init__(self, settings: IngestSettings, task_queue: TaskQueue) -> None:
        self.settings = settings
        self.task_queue = task_queue

    async def __call__(self, event: events.NewMessage.Event) -> None:
        async for attempt in AsyncRetrying(
            retry=retry_if_exception_type(OperationalError),
            wait=wait_random_exponential(multiplier=1, max=30),
            stop=stop_after_attempt(5),
            reraise=True,
        ):
            with attempt:
                await self._handle(event)

    async def _handle(self, event: events.NewMessage.Event) -> None:
        message = event.message
        if not message:
            return

        peer = getattr(message, "peer_id", None)
        tg_channel_id = getattr(peer, "channel_id", None)
        if tg_channel_id is None:
            logger.debug("Ignored non-channel message")
            return

        raw_text = normalize_text(message.message or "")
        if not raw_text:
            logger.debug(
                "Empty message ignored",
                extra={"channel": tg_channel_id, "message_id": message.id},
            )
            return

        channel_title = getattr(getattr(event, "chat", None), "title", None)

        channel_id = await get_or_create_channel(self.settings.database_url, tg_channel_id, channel_title)
        post_id, is_new = await upsert_post(
            self.settings.database_url,
            channel_id=channel_id,
            message_id=message.id,
            published_at=message.date,
            raw_text=raw_text,
        )
        if not is_new:
            logger.debug(
                "Post already processed",
                extra={"post_id": post_id, "channel_id": channel_id, "tg_channel_id": tg_channel_id},
            )
            return

        self.task_queue.send_summarize_task(post_id)


def normalize_text(text_value: str) -> str:
    text_value = text_value.replace("\u200b", "").replace("\ufeff", "")
    text_value = text_value.strip()
    if len(text_value) > MAX_MESSAGE_LEN:
        text_value = text_value[: MAX_MESSAGE_LEN - len(TRIMMING_SUFFIX)] + TRIMMING_SUFFIX
    return text_value


async def load_channel_ids(settings: IngestSettings) -> List[int]:
    if settings.channel_source == "env":
        return settings.channel_ids

    async with session_scope(settings.database_url) as session:
        rs = await session.execute(text("SELECT tg_channel_id FROM channels WHERE tg_channel_id IS NOT NULL"))
        return [int(row[0]) for row in rs]


def distribute_channels(session_files: Sequence[Path], channel_ids: Sequence[int]) -> Dict[Path, List[int]]:
    if not session_files:
        return {}
    mapping: Dict[Path, List[int]] = {session: [] for session in session_files}
    iterator = cycle(session_files)
    for channel_id in channel_ids:
        session = next(iterator)
        mapping[session].append(channel_id)
    return mapping


async def run_worker() -> int:
    settings = load_settings()
    logging.getLogger().setLevel(settings.log_level.upper())

    session_files = sorted(settings.sessions_dir.glob("*.session"))
    if not session_files:
        logger.error("No Telethon session files found", extra={"sessions_dir": str(settings.sessions_dir)})
        return 1

    channel_ids = await load_channel_ids(settings)
    if not channel_ids:
        logger.warning("No channels configured for ingest")

    queue_app = create_celery_app(settings.celery_broker, settings.celery_backend)
    task_queue = TaskQueue(queue_app, settings.queue_summarize)
    processor = MessageProcessor(settings, task_queue)

    assignments = distribute_channels(session_files, channel_ids or [])
    shards = []
    for session_path, assigned_channels in assignments.items():
        if not assigned_channels:
            logger.info(
                "Skipping session without assigned channels",
                extra={"session": str(session_path)},
            )
            continue
        shard = TelethonShard(
            session_path=session_path,
            api_id=settings.tg_api_id,
            api_hash=settings.tg_api_hash,
            channels=assigned_channels,
            handler=processor,
        )
        shards.append(shard)

    if not shards:
        logger.error("No shards created; ensure channels are configured")
        return 1

    await asyncio.gather(*(shard.run() for shard in shards))
    return 0


def main() -> None:
    try:
        exit_code = asyncio.run(run_worker())
    except KeyboardInterrupt:
        logger.info("Shutting down ingest service due to keyboard interrupt")
        exit_code = 0
    except Exception:
        logger.exception("Fatal error in ingest worker")
        exit_code = 1
    sys.exit(exit_code)
