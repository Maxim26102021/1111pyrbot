from __future__ import annotations

import asyncio
import importlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest


def test_smoke_flow(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("LLM_MODE", "mock")
    monkeypatch.setenv("REDIS_URL", "redis://mock")
    monkeypatch.setenv("DATABASE_URL", "postgresql://user:pass@localhost/db")
    monkeypatch.setenv("BOT_TOKEN", "123456:TESTTOKEN")

    dev_fake_ingest = importlib.import_module("scripts.dev_fake_ingest")
    scheduler_tasks = importlib.import_module("services.scheduler.app.tasks")
    bot_tasks = importlib.import_module("services.bot.app.tasks")
    bot_messaging = importlib.import_module("services.bot.app.messaging")

    db = {
        "channels": {},
        "posts": {},
        "summaries": {},
        "digests": [],
        "users": {1: {"id": 1, "tg_user_id": 999}},
        "user_channels": {1: []},
        "bot_messages": [],
    }

    async def fake_ensure_channel(database_url, handle, title, tg_channel_id):
        channel_id = len(db["channels"]) + 1
        db["channels"][channel_id] = {
            "id": channel_id,
            "handle": handle,
            "title": title,
            "tg_id": tg_channel_id,
        }
        db["user_channels"][1] = [channel_id]
        return channel_id

    async def fake_insert_post(database_url, channel_id, message_id, published_at, text_body):
        post_id = len(db["posts"]) + 1
        db["posts"][post_id] = {
            "channel_id": channel_id,
            "message_id": message_id,
            "published_at": published_at,
            "text": text_body,
        }
        return post_id

    def fake_enqueue(post_id: int, priority: bool = False) -> None:
        db["summaries"][post_id] = {
            "channel_id": db["posts"][post_id]["channel_id"],
            "summary_text": f"Mock summary for post {post_id}",
            "created_at": datetime.now(timezone.utc),
        }

    async def fake_get_active_users(database_url):
        return [(1, db["users"][1]["tg_user_id"], None)]

    async def fake_get_user_channels(database_url, user_id):
        return db["user_channels"].get(user_id, [])

    async def fake_get_recent(database_url, channel_ids, since_dt):
        results = []
        for post_id, info in db["summaries"].items():
            if info["channel_id"] in channel_ids:
                results.append((post_id, info["channel_id"], info["summary_text"], info["created_at"]))
        return results

    async def fake_insert_digest(database_url, user_id, slot, summaries):
        digest_id = len(db["digests"]) + 1
        db["digests"].append({"id": digest_id, "user_id": user_id, "summaries": summaries})
        return digest_id

    send_calls = []

    def fake_send_task(name, args=None, queue=None, **kwargs):
        send_calls.append({"name": name, "args": args, "queue": queue})

    async def fake_send_text(tg_user_id, text, parse_mode=None):
        db["bot_messages"].append({"user_id": tg_user_id, "text": text})
        return 1

    monkeypatch.setattr(dev_fake_ingest, "ensure_channel", fake_ensure_channel)
    monkeypatch.setattr(dev_fake_ingest, "insert_post", fake_insert_post)
    monkeypatch.setattr(dev_fake_ingest, "enqueue_summarize", fake_enqueue)

    monkeypatch.setattr(scheduler_tasks, "get_active_users", fake_get_active_users)
    monkeypatch.setattr(scheduler_tasks, "get_user_channels", fake_get_user_channels)
    monkeypatch.setattr(scheduler_tasks, "get_recent_summaries", fake_get_recent)
    monkeypatch.setattr(scheduler_tasks, "insert_digest", fake_insert_digest)
    monkeypatch.setattr(scheduler_tasks.celery_app, "send_task", fake_send_task)
    monkeypatch.setattr(bot_messaging, "send_text", fake_send_text)
    monkeypatch.setattr(bot_tasks, "send_text", fake_send_text)

    args = SimpleNamespace(
        database_url="mock://db",
        channel="Demo",
        tg_channel_id=1001,
        message_id=42,
        text="Тестовый пост",
        published_at=None,
        priority=False,
    )

    asyncio.run(dev_fake_ingest.run(args))

    scheduler_tasks.build_and_dispatch_digest()

    assert db["digests"], "Digest should be created"
    assert send_calls, "Digest send task should be queued"

    # simulate bot delivery
    for call in send_calls:
        if call["name"] == "send_digest":
            bot_tasks.send_digest.apply(args=call["args"])

    assert db["bot_messages"], "Bot should have messages ready"
