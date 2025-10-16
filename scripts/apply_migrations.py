from __future__ import annotations

import asyncio
import logging
import os
from pathlib import Path

from sqlalchemy import text

from libs.core.pg import build_engine

logger = logging.getLogger("migrations")
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)

MIGRATIONS_DIR = Path(__file__).resolve().parent.parent / "migrations"


async def apply_migration(engine, file_path: Path) -> None:
    sql = file_path.read_text()
    async with engine.begin() as conn:
        logger.info("Applying migration %s", file_path.name)
        await conn.exec_driver_sql(sql)
        logger.info("Migration %s applied", file_path.name)


async def run() -> None:
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL env variable is required")

    engine = build_engine(database_url)
    try:
        files = sorted(MIGRATIONS_DIR.glob("*.sql"))
        if not files:
            logger.warning("No migrations found in %s", MIGRATIONS_DIR)
            return

        for file_path in files:
            await apply_migration(engine, file_path)
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(run())
