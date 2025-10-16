from __future__ import annotations

from typing import Any, Dict, Optional

from sqlalchemy import text

from libs.core.pg import session_scope


async def fetch_post(database_url: str, post_id: int) -> Optional[Dict[str, Any]]:
    query = text(
        """
        SELECT id, channel_id, message_id, published_at, text_hash, raw_text
        FROM posts
        WHERE id = :post_id
        """
    )
    async with session_scope(database_url) as session:
        result = await session.execute(query, {"post_id": post_id})
        row = result.mappings().first()
        return dict(row) if row else None


async def upsert_summary(
    database_url: str,
    *,
    post_id: int,
    summary_text: str,
    model: str,
    tokens_in: Optional[int],
    tokens_out: Optional[int],
    cost: Optional[float],
) -> None:
    query = text(
        """
        INSERT INTO summaries (post_id, summary_text, model, tokens_in, tokens_out, cost)
        VALUES (:post_id, :summary_text, :model, :tokens_in, :tokens_out, :cost)
        ON CONFLICT (post_id) DO UPDATE
        SET summary_text = EXCLUDED.summary_text,
            model = EXCLUDED.model,
            tokens_in = EXCLUDED.tokens_in,
            tokens_out = EXCLUDED.tokens_out,
            cost = EXCLUDED.cost,
            created_at = NOW()
        """
    )
    async with session_scope(database_url) as session:
        await session.execute(
            query,
            {
                "post_id": post_id,
                "summary_text": summary_text,
                "model": model,
                "tokens_in": tokens_in,
                "tokens_out": tokens_out,
                "cost": cost,
            },
        )


async def find_summary_by_post(database_url: str, post_id: int) -> Optional[Dict[str, Any]]:
    query = text(
        """
        SELECT post_id, summary_text, model, tokens_in, tokens_out, cost
        FROM summaries
        WHERE post_id = :post_id
        """
    )
    async with session_scope(database_url) as session:
        result = await session.execute(query, {"post_id": post_id})
        row = result.mappings().first()
        return dict(row) if row else None


async def find_post_by_text_hash(database_url: str, text_hash: str, *, exclude_post_id: Optional[int] = None) -> Optional[int]:
    if not text_hash:
        return None

    query = text(
        """
        SELECT id
        FROM posts
        WHERE text_hash = :text_hash
          AND (:exclude_post_id IS NULL OR id <> :exclude_post_id)
        ORDER BY created_at ASC
        LIMIT 1
        """
    )
    async with session_scope(database_url) as session:
        result = await session.execute(
            query,
            {"text_hash": text_hash, "exclude_post_id": exclude_post_id},
        )
        value = result.scalar()
        return int(value) if value is not None else None
