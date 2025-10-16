from __future__ import annotations

import logging
from datetime import datetime

from sqlalchemy import text

from libs.core.pg import session_scope
from libs.core.util import hash_text

logger = logging.getLogger(__name__)


async def get_or_create_channel(database_url: str, tg_channel_id: int, title: str | None) -> int:
    query = text(
        """
        INSERT INTO channels (tg_channel_id, title)
        VALUES (:channel_id, COALESCE(:title, title))
        ON CONFLICT (tg_channel_id) DO UPDATE
        SET title = COALESCE(EXCLUDED.title, channels.title)
        RETURNING id
        """
    )
    async with session_scope(database_url) as session:
        result = await session.execute(query, {"channel_id": tg_channel_id, "title": title})
        channel_id = result.scalar_one()
        logger.debug("Ensured channel", extra={"channel_id": channel_id, "tg_channel_id": tg_channel_id})
        return int(channel_id)


async def upsert_post(
    database_url: str,
    *,
    channel_id: int,
    message_id: int,
    published_at: datetime | None,
    raw_text: str,
) -> tuple[int, bool]:
    text_hash_value = hash_text(raw_text)
    select_query = text(
        """
        SELECT id FROM posts WHERE channel_id = :channel_id AND message_id = :message_id
        """
    )
    insert_query = text(
        """
        INSERT INTO posts (channel_id, message_id, published_at, text_hash, raw_text)
        VALUES (:channel_id, :message_id, :published_at, :text_hash, :raw_text)
        RETURNING id
        """
    )

    async with session_scope(database_url) as session:
        existing = await session.execute(
            select_query,
            {"channel_id": channel_id, "message_id": message_id},
        )
        existing_id = existing.scalar()
        if existing_id:
            logger.debug(
                "Post already ingested",
                extra={"channel_id": channel_id, "message_id": message_id, "post_id": existing_id},
            )
            return int(existing_id), False

        result = await session.execute(
            insert_query,
            {
                "channel_id": channel_id,
                "message_id": message_id,
                "published_at": published_at,
                "text_hash": text_hash_value,
                "raw_text": raw_text,
            },
        )
        post_id = result.scalar_one()
        logger.info(
            "Stored new post",
            extra={"post_id": post_id, "channel_id": channel_id, "message_id": message_id},
        )
        return int(post_id), True
