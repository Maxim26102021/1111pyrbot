from __future__ import annotations

import asyncio
import importlib
import sys
from types import SimpleNamespace

import pytest


REQUIRED_ENV = {
    "BOT_TOKEN": "123456:TESTTOKEN",
    "REDIS_URL": "redis://localhost:6379/0",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
}


def reload_bot(monkeypatch: pytest.MonkeyPatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)

    for module in [
        "services.bot.app.handlers",
        "services.bot.app.bot",
        "services.bot.app.messaging",
        "services.bot.app.dao",
        "services.bot.app.config",
        "services.bot.app.celery_app",
        "services.bot.app.tasks",
    ]:
        sys.modules.pop(module, None)

    bot_module = importlib.import_module("services.bot.app.bot")
    messaging_module = importlib.import_module("services.bot.app.messaging")
    handlers_module = importlib.import_module("services.bot.app.handlers")
    dao_module = importlib.import_module("services.bot.app.dao")
    tasks_module = importlib.import_module("services.bot.app.tasks")
    return bot_module, messaging_module, handlers_module, dao_module, tasks_module


class DummyMessage:
    def __init__(self, user_id: int, bot):
        self.from_user = SimpleNamespace(id=user_id, language_code="ru")
        self.bot = bot
        self.sent_texts = []

    async def answer(self, text: str):
        self.sent_texts.append(text)

        class DummyResponse:
            def __init__(self, collector):
                self.collector = collector

            async def edit_text(self, text: str):
                self.collector.append(text)

        return DummyResponse(self.sent_texts)


def test_preview_sample_triggers_send_digest(monkeypatch: pytest.MonkeyPatch):
    bot_module, messaging_module, handlers_module, dao_module, tasks_module = reload_bot(monkeypatch)

    summaries = [
        {"channel_title": "Канал 1", "summary_text": "Новости"},
    ]

    async def fake_upsert(*args, **kwargs):
        return None

    async def fake_fetch_summaries(*args, **kwargs):
        return summaries

    async def fake_posts(*args, **kwargs):
        return []

    monkeypatch.setattr(handlers_module, "upsert_user", fake_upsert)
    monkeypatch.setattr(handlers_module, "fetch_preview_summaries", fake_fetch_summaries)
    monkeypatch.setattr(handlers_module, "fetch_recent_posts_without_summary", fake_posts)

    tasks_called = {}

    def fake_delay(user_id, text, parse_mode=None):
        tasks_called["user_id"] = user_id
        tasks_called["text"] = text
        tasks_called["parse_mode"] = parse_mode

    monkeypatch.setattr(tasks_module.send_digest, "delay", fake_delay)

    message = DummyMessage(user_id=123, bot=messaging_module.bot)

    asyncio.run(handlers_module.cmd_preview_sample(message))

    assert tasks_called["user_id"] == 123
    assert "Канал 1" in tasks_called["text"]
