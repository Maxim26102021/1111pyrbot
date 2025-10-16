from __future__ import annotations

import asyncio
import importlib
import sys
from datetime import datetime, timedelta, timezone

import pytest


REQUIRED_ENV = {
    "REDIS_URL": "redis://localhost:6379/0",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    "QUEUE_DIGEST": "digest",
    "QUEUE_BOT": "bot",
}


def reload_scheduler(monkeypatch: pytest.MonkeyPatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    for module_name in [
        "services.scheduler.app.tasks",
        "services.scheduler.app.celery_app",
        "services.scheduler.app.config",
    ]:
        sys.modules.pop(module_name, None)

    tasks_module = importlib.import_module("services.scheduler.app.tasks")
    return tasks_module


@pytest.fixture
def tasks(monkeypatch: pytest.MonkeyPatch):
    module = reload_scheduler(monkeypatch)
    return module


def run_async(coro):
    return asyncio.run(coro)


def test_build_and_dispatch_creates_digest(tasks, monkeypatch):
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
    active_users = [(1, 1001, "ru")]
    channels = [10]
    summaries = [(101, 10, "Summary text", now - timedelta(minutes=1))]
    recorded = {}

    async def fake_active_users(database_url):
        return active_users

    async def fake_user_channels(database_url, user_id):
        return channels

    async def fake_recent(database_url, channel_ids, since_dt):
        recorded["since"] = since_dt
        return summaries

    async def fake_insert(database_url, **kwargs):
        recorded["insert"] = kwargs
        return 555

    def fake_send_task(name, args=None, queue=None, **kwargs):
        recorded["task"] = (name, args, queue)

    monkeypatch.setattr(tasks, "get_active_users", fake_active_users)
    monkeypatch.setattr(tasks, "get_user_channels", fake_user_channels)
    monkeypatch.setattr(tasks, "get_recent_summaries", fake_recent)
    monkeypatch.setattr(tasks, "insert_digest", fake_insert)
    monkeypatch.setattr(tasks.celery_app, "send_task", fake_send_task)

    run_async(tasks._build_and_dispatch(now))  # noqa: SLF001

    assert recorded["task"] == ("send_digest", [1, "• Канал 10: Summary text"], "bot")
    assert recorded["insert"]["user_id"] == 1
    assert recorded["insert"]["slot"].startswith("2024-01-01T12:00:00")


def test_build_and_dispatch_skips_when_no_summaries(tasks, monkeypatch):
    now = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)

    async def fake_active_users(database_url):
        return [(1, 1001, "ru")]

    async def fake_channels(database_url, user_id):
        return [10]

    async def fake_recent(database_url, channel_ids, since_dt):
        return []

    monkeypatch.setattr(tasks, "get_active_users", fake_active_users)
    monkeypatch.setattr(tasks, "get_user_channels", fake_channels)
    monkeypatch.setattr(tasks, "get_recent_summaries", fake_recent)

    called = False

    async def fake_insert(*args, **kwargs):  # pragma: no cover
        nonlocal called
        called = True
        return 555

    def fake_send_task(*args, **kwargs):  # pragma: no cover
        nonlocal called
        called = True

    monkeypatch.setattr(tasks, "insert_digest", fake_insert)
    monkeypatch.setattr(tasks.celery_app, "send_task", fake_send_task)

    run_async(tasks._build_and_dispatch(now))  # noqa: SLF001

    assert not called
