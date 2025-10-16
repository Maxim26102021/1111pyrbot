from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Sequence, Tuple

from sqlalchemy import text

from libs.core.pg import session_scope


async def get_active_users(database_url: str) -> List[Tuple[int, int, str | None]]:
    query = text(
        """
        SELECT DISTINCT u.id, u.tg_user_id, u.lang
        FROM users u
        JOIN subscriptions s ON s.user_id = u.id
        WHERE s.status = 'active'
        """
    )
    async with session_scope(database_url) as session:
        rows = await session.execute(query)
        return [tuple(row) for row in rows]


async def get_user_channels(database_url: str, user_id: int) -> List[int]:
    query = text(
        """
        SELECT channel_id
        FROM user_channels
        WHERE user_id = :user_id
        """
    )
    async with session_scope(database_url) as session:
        rows = await session.execute(query, {"user_id": user_id})
        return [int(row[0]) for row in rows]


async def get_recent_summaries(
    database_url: str,
    channel_ids: Sequence[int],
    since_dt: datetime,
) -> List[Tuple[int, int, str, datetime]]:
    if not channel_ids:
        return []
    query = text(
        """
        SELECT p.id, p.channel_id, s.summary_text, s.created_at
        FROM posts p
        JOIN summaries s ON s.post_id = p.id
        WHERE p.channel_id = ANY(:channel_ids)
          AND s.created_at >= :since
        ORDER BY s.created_at DESC
        LIMIT 100
        """
    )
    async with session_scope(database_url) as session:
        rows = await session.execute(
            query,
            {"channel_ids": list(channel_ids), "since": since_dt},
        )
        return [tuple(row) for row in rows]


async def insert_digest(
    database_url: str,
    *,
    user_id: int,
    slot: str,
    summaries: Sequence[Tuple[int, int, str, datetime]],
) -> int:
    if not summaries:
        raise ValueError("summaries must not be empty")

    insert_digest_query = text(
        """
        INSERT INTO digests (user_id, slot)
        VALUES (:user_id, :slot)
        RETURNING id
        """
    )

    insert_item_query = text(
        """
        INSERT INTO digest_items (digest_id, post_id, order_index)
        VALUES (:digest_id, :post_id, :order_index)
        """
    )

    async with session_scope(database_url) as session:
        result = await session.execute(
            insert_digest_query,
            {"user_id": user_id, "slot": slot},
        )
        digest_id = result.scalar_one()

        for order_index, (post_id, _, _, _) in enumerate(summaries):
            await session.execute(
                insert_item_query,
                {"digest_id": digest_id, "post_id": post_id, "order_index": order_index},
            )

        return int(digest_id)
