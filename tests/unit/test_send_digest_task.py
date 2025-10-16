from __future__ import annotations

import asyncio
import importlib
import sys

import pytest


REQUIRED_ENV = {
    "BOT_TOKEN": "123456:TESTTOKEN",
    "REDIS_URL": "redis://localhost:6379/0",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
}


def reload_bot_modules(monkeypatch: pytest.MonkeyPatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    for module in [
        "services.bot.app.tasks",
        "services.bot.app.bot",
        "services.bot.app.messaging",
        "services.bot.app.config",
        "services.bot.app.celery_app",
    ]:
        sys.modules.pop(module, None)

    bot_module = importlib.import_module("services.bot.app.messaging")
    tasks_module = importlib.import_module("services.bot.app.tasks")
    return bot_module, tasks_module


def test_send_text_splits_message(monkeypatch):
    bot_module, _ = reload_bot_modules(monkeypatch)

    chunks_recorded = []

    async def fake_send_chunk(user_id, text, parse_mode):
        chunks_recorded.append(text)

    monkeypatch.setattr(bot_module, "_send_chunk", fake_send_chunk)

    long_text = "A" * (bot_module.settings.telegram_max_message + 10)
    asyncio.run(bot_module.send_text(123, long_text))

    assert len(chunks_recorded) == 2
    assert all(len(c) <= bot_module.settings.telegram_max_message for c in chunks_recorded)


def test_send_text_handles_flood_wait(monkeypatch):
    bot_module, _ = reload_bot_modules(monkeypatch)

    class DummyRetry(Exception):
        def __init__(self, retry_after):
            super().__init__("retry")
            self.retry_after = retry_after

    monkeypatch.setattr(bot_module, "TelegramRetryAfter", DummyRetry)

    calls = {"count": 0}

    async def fake_send_chunk(user_id, text, parse_mode):
        if calls["count"] == 0:
            calls["count"] += 1
            raise DummyRetry(0.1)
        calls["count"] += 1

    monkeypatch.setattr(bot_module, "_send_chunk", fake_send_chunk)

    asyncio.run(bot_module.send_text(123, "hello"))
    assert calls["count"] == 2


def test_send_digest_retries_on_retryable(monkeypatch):
    bot_module, tasks_module = reload_bot_modules(monkeypatch)

    def fake_send_text(user_id, text, parse_mode=None):
        raise bot_module.RetryableTelegramError()

    monkeypatch.setattr(tasks_module, "send_text", fake_send_text)

    with pytest.raises(bot_module.RetryableTelegramError):
        tasks_module.send_digest.run(123, "text")


def test_send_digest_ignores_fatal(monkeypatch):
    bot_module, tasks_module = reload_bot_modules(monkeypatch)

    def fake_send_text(user_id, text, parse_mode=None):
        raise bot_module.FatalTelegramError("blocked")

    monkeypatch.setattr(tasks_module, "send_text", fake_send_text)

    tasks_module.send_digest.run(123, "text")
