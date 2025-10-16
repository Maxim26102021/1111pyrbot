from __future__ import annotations

from typing import Any

from redis.asyncio import Redis


def build_redis(url: str, *, decode_responses: bool = True) -> Redis:
    """Create a Redis client instance."""
    return Redis.from_url(url, decode_responses=decode_responses)


async def ping(client: Redis) -> bool:
    """Simple health-check helper for Redis."""
    try:
        return bool(await client.ping())
    except Exception:
        return False
