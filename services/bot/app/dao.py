from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

from sqlalchemy import text

from libs.core.pg import session_scope


async def upsert_user(database_url: str, tg_user_id: int, lang: Optional[str]) -> None:
    query = text(
        """
        INSERT INTO users (tg_user_id, lang)
        VALUES (:tg_user_id, :lang)
        ON CONFLICT (tg_user_id) DO UPDATE
        SET lang = COALESCE(EXCLUDED.lang, users.lang)
        """
    )
    async with session_scope(database_url) as session:
        await session.execute(query, {"tg_user_id": tg_user_id, "lang": lang})


async def fetch_preview_summaries(database_url: str, *, limit: int) -> List[Dict[str, Any]]:
    query = text(
        """
        SELECT s.post_id, p.channel_id, COALESCE(c.title, CONCAT('Channel ', p.channel_id)) AS channel_title,
               s.summary_text, s.created_at
        FROM summaries s
        JOIN posts p ON p.id = s.post_id
        LEFT JOIN channels c ON c.id = p.channel_id
        ORDER BY s.created_at DESC
        LIMIT :limit
        """
    )
    async with session_scope(database_url) as session:
        rows = await session.execute(query, {"limit": limit})
        return [dict(row) for row in rows.mappings()]


async def fetch_recent_posts_without_summary(database_url: str, *, limit: int) -> List[int]:
    query = text(
        """
        SELECT p.id
        FROM posts p
        LEFT JOIN summaries s ON s.post_id = p.id
        WHERE s.post_id IS NULL
        ORDER BY p.created_at DESC
        LIMIT :limit
        """
    )
    async with session_scope(database_url) as session:
        rows = await session.execute(query, {"limit": limit})
        return [int(row[0]) for row in rows]
