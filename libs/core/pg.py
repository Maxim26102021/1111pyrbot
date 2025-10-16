from __future__ import annotations

from contextlib import asynccontextmanager
from functools import lru_cache
from typing import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)


@lru_cache(maxsize=1)
def build_engine(database_url: str) -> AsyncEngine:
    """Create (and cache) an async SQLAlchemy engine."""
    return create_async_engine(
        database_url,
        future=True,
        pool_pre_ping=True,
    )


def session_factory(database_url: str) -> async_sessionmaker[AsyncSession]:
    """Return an async session factory bound to the cached engine."""
    return async_sessionmaker(
        bind=build_engine(database_url),
        expire_on_commit=False,
    )


@asynccontextmanager
async def session_scope(database_url: str) -> AsyncIterator[AsyncSession]:
    """Async context manager that commits or rolls back automatically."""
    factory = session_factory(database_url)
    async with factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
