from __future__ import annotations

import asyncio
import os
import subprocess
import time
from pathlib import Path

import pytest
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from libs.core.pg import build_engine

ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = ROOT / "deploy" / "docker-compose.yml"
TEST_DATABASE_URL = "postgresql+asyncpg://digest:digest@localhost:5433/digest"


def _run_compose(*args: str) -> None:
    try:
        subprocess.run(
            ["docker", "compose", "-f", str(COMPOSE_FILE), *args],
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        pytest.skip(f"docker command not available: {exc}")
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr or ""
        if "Cannot connect to the Docker daemon" in stderr or "permission denied" in stderr:
            pytest.skip(f"docker daemon unavailable: {stderr.strip()}")
        raise


@pytest.fixture(scope="session", autouse=True)
def ensure_infra() -> None:
    _run_compose("up", "-d", "postgres", "redis")
    _wait_for_postgres()
    yield
    _run_compose("down")


@pytest.mark.asyncio
async def test_migrations_apply_and_tables_exist(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE_URL", TEST_DATABASE_URL)

    proc = subprocess.run(
        ["python", str(ROOT / "scripts" / "apply_migrations.py")],
        capture_output=True,
        text=True,
        check=True,
        env=os.environ.copy(),
    )
    assert "Applying migration" in proc.stdout + proc.stderr

    engine = build_engine(TEST_DATABASE_URL)
    try:
        async with engine.connect() as conn:
            result = await conn.execute(
                text(
                    """
                    SELECT table_name
                    FROM information_schema.tables
                    WHERE table_schema = 'public'
                      AND table_name IN ('users', 'posts', 'summaries', 'subscriptions')
                    """
                )
            )
            tables = {row[0] for row in result}
    finally:
        await engine.dispose()

    assert {"users", "posts", "summaries", "subscriptions"}.issubset(tables)


def _wait_for_postgres(timeout: int = 60) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            asyncio.run(_probe_connection())
            return
        except Exception:
            time.sleep(1)
    raise TimeoutError("Postgres did not become ready in time")


async def _probe_connection() -> None:
    engine = create_async_engine(TEST_DATABASE_URL, future=True)
    try:
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
    finally:
        await engine.dispose()
