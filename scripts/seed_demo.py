from __future__ import annotations

import asyncio
import os
from datetime import datetime, timezone, timedelta

from sqlalchemy import text

from libs.core.pg import session_scope


async def seed(database_url: str) -> None:
    async with session_scope(database_url) as session:
        user = await session.execute(
            text(
                """
                INSERT INTO users (tg_user_id, plan) VALUES (999, 'pro')
                ON CONFLICT (tg_user_id) DO NOTHING
                RETURNING id
                """
            )
        )
        user_id = user.scalar()
        if not user_id:
            result = await session.execute(text("SELECT id FROM users WHERE tg_user_id=999"))
            user_id = result.scalar()

        channel = await session.execute(
            text(
                """
                INSERT INTO channels (tg_channel_id, handle, title)
                VALUES (1001, 'demo_channel', 'Demo Channel')
                ON CONFLICT (tg_channel_id) DO UPDATE SET title='Demo Channel'
                RETURNING id
                """
            )
        )
        channel_id = channel.scalar()

        await session.execute(
            text(
                """
                INSERT INTO user_channels (user_id, channel_id)
                VALUES (:user_id, :channel_id)
                ON CONFLICT DO NOTHING
                """
            ),
            {"user_id": user_id, "channel_id": channel_id},
        )

        await session.execute(
            text(
                """
                INSERT INTO subscriptions (user_id, status, plan, paid_until)
                VALUES (:user_id, 'active', 'pro', :paid_until)
                ON CONFLICT (user_id) DO UPDATE SET status='active'
                """
            ),
            {"user_id": user_id, "paid_until": datetime.now(timezone.utc) + timedelta(days=30)},
        )


if __name__ == "__main__":
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise SystemExit("DATABASE_URL environment variable is required")

    asyncio.run(seed(database_url))
