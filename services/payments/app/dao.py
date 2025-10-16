from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Dict, Optional

import json

from sqlalchemy import text

from libs.core.pg import session_scope


async def get_user_by_ids(database_url: str, *, user_id: Optional[int], tg_user_id: Optional[int]) -> Optional[Dict[str, Any]]:
    if not user_id and not tg_user_id:
        return None

    query = text(
        """
        SELECT * FROM users
        WHERE (:user_id IS NULL OR id = :user_id)
          OR (:tg_user_id IS NULL OR tg_user_id = :tg_user_id)
        LIMIT 1
        """
    )
    async with session_scope(database_url) as session:
        result = await session.execute(query, {"user_id": user_id, "tg_user_id": tg_user_id})
        row = result.mappings().first()
        return dict(row) if row else None


async def insert_payment_idempotent(
    database_url: str,
    *,
    user_id: int,
    provider: str,
    ext_id: str,
    amount: Decimal,
    currency: str,
    status: str,
    payload: Dict[str, Any],
) -> Dict[str, Any]:
    query = text(
        """
        INSERT INTO payments (user_id, provider, ext_id, amount, currency, status, payload)
        VALUES (:user_id, :provider, :ext_id, :amount, :currency, :status, :payload)
        ON CONFLICT (provider, ext_id) DO UPDATE
        SET status = EXCLUDED.status,
            payload = EXCLUDED.payload
        RETURNING *
        """
    )
    async with session_scope(database_url) as session:
        payload_json = json.dumps(payload)
        result = await session.execute(
            query,
            {
                "user_id": user_id,
                "provider": provider,
                "ext_id": ext_id,
                "amount": amount,
                "currency": currency,
                "status": status,
                "payload": payload_json,
            },
        )
        row = result.mappings().first()
        return dict(row)


async def activate_subscription(database_url: str, user_id: int, plan: str, days: int) -> None:
    now = datetime.now(timezone.utc)
    query_select = text(
        """
        SELECT * FROM subscriptions WHERE user_id = :user_id LIMIT 1
        """
    )
    async with session_scope(database_url) as session:
        result = await session.execute(query_select, {"user_id": user_id})
        existing = result.mappings().first()

        if existing:
            paid_until = existing.get("paid_until") or now
            if paid_until < now:
                new_paid_until = now + timedelta(days=days)
            else:
                new_paid_until = paid_until + timedelta(days=days)

            await session.execute(
                text(
                    """
                    UPDATE subscriptions
                    SET status='active', plan=:plan, paid_until=:paid_until
                    WHERE id=:id
                    """
                ),
                {"plan": plan, "paid_until": new_paid_until, "id": existing["id"]},
            )
        else:
            new_paid_until = now + timedelta(days=days)
            await session.execute(
                text(
                    """
                    INSERT INTO subscriptions (user_id, status, plan, paid_until)
                    VALUES (:user_id, 'active', :plan, :paid_until)
                    """
                ),
                {"user_id": user_id, "plan": plan, "paid_until": new_paid_until},
            )
