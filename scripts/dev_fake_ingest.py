from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from hashlib import sha256

from sqlalchemy import text

from libs.core.logging import json_log
from libs.core.pg import session_scope
logger = logging.getLogger(__name__)


async def ensure_channel(database_url: str, handle: str, title: str, tg_channel_id: int) -> int:
    from common.models import ensure_channel as models_ensure_channel

    channel = models_ensure_channel(handle)
    query = text(
        """
        UPDATE channels
        SET tg_channel_id = COALESCE(tg_channel_id, :tg_id), title = COALESCE(title, :title)
        WHERE id = :id
        """
    )
    async with session_scope(database_url) as session:
        await session.execute(query, {"tg_id": tg_channel_id, "title": title, "id": channel["id"]})
    return channel["id"]


async def insert_post(
    database_url: str,
    *,
    channel_id: int,
    message_id: int,
    published_at: datetime,
    text_body: str,
) -> int:
    query = text(
        """
        INSERT INTO posts (channel_id, message_id, published_at, text_hash, raw_text)
        VALUES (:channel_id, :message_id, :published_at, :text_hash, :raw_text)
        ON CONFLICT (channel_id, message_id) DO UPDATE
        SET raw_text = EXCLUDED.raw_text
        RETURNING id
        """
    )
    text_hash = sha256(text_body.encode("utf-8")).hexdigest()
    async with session_scope(database_url) as session:
        result = await session.execute(
            query,
            {
                "channel_id": channel_id,
                "message_id": message_id,
                "published_at": published_at,
                "text_hash": text_hash,
                "raw_text": text_body,
            },
        )
        return int(result.scalar_one())


def enqueue_summarize(post_id: int, priority: bool = False) -> None:
    from services.summarizer.app.tasks import summarize_post

    summarize_post.delay(post_id, priority=priority)


async def run(args) -> None:
    published_at = (
        datetime.fromisoformat(args.published_at)
        if args.published_at
        else datetime.now(timezone.utc)
    )
    channel_id = await ensure_channel(args.database_url, args.channel, args.channel, args.tg_channel_id)
    post_id = await insert_post(
        args.database_url,
        channel_id=channel_id,
        message_id=args.message_id,
        published_at=published_at,
        text_body=args.text,
    )
    enqueue_summarize(post_id, priority=args.priority)
    json_log(
        logger,
        "info",
        "dev_fake_ingest",
        service="dev-tools",
        post_id=post_id,
        channel_id=channel_id,
        message_id=args.message_id,
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Inject a fake post for development.")
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"), help="Database URL")
    parser.add_argument("--channel", required=True, help="Channel handle or title")
    parser.add_argument("--tg_channel_id", type=int, required=True, help="Telegram channel id")
    parser.add_argument("--message_id", type=int, required=True, help="Telegram message id")
    parser.add_argument("--text", required=True, help="Post text content")
    parser.add_argument("--published_at", help="ISO datetime string (defaults to now)")
    parser.add_argument("--priority", action="store_true", help="Use priority summarization queue")
    args = parser.parse_args()
    if not args.database_url:
        parser.error("DATABASE_URL must be provided via argument or environment")
    return args


if __name__ == "__main__":
    import os
    import logging

    from libs.core.logging import json_log

    logging.basicConfig(level="INFO", format="%(message)s")
    logger = logging.getLogger(__name__)

    arguments = parse_args()
    asyncio.run(run(arguments))
