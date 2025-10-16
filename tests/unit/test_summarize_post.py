from __future__ import annotations

import asyncio
import importlib
import os
import sys
from types import SimpleNamespace

import pytest


REQUIRED_ENV = {
    "REDIS_URL": "redis://localhost:6379/0",
    "DATABASE_URL": "postgresql+asyncpg://user:pass@localhost:5432/db",
    "OPENAI_API_KEY": "test-key",
}


def reload_tasks(monkeypatch: pytest.MonkeyPatch):
    for key, value in REQUIRED_ENV.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setenv("CELERY_BROKER_URL", REQUIRED_ENV["REDIS_URL"])
    monkeypatch.setenv("CELERY_RESULT_BACKEND", REQUIRED_ENV["REDIS_URL"])

    for module_name in [
        "services.summarizer.app.tasks",
        "services.summarizer.app.celery_app",
        "services.summarizer.app.config",
    ]:
        sys.modules.pop(module_name, None)

    tasks_module = importlib.import_module("services.summarizer.app.tasks")
    return tasks_module


@pytest.fixture
def tasks(monkeypatch: pytest.MonkeyPatch):
    module = reload_tasks(monkeypatch)
    return module


def run_async(coro):
    return asyncio.run(coro)


def test_short_text_creates_technical_summary(tasks, monkeypatch):
    captured = {}

    async def fake_fetch_post(database_url, post_id):
        return {"id": post_id, "channel_id": 1, "raw_text": "hi", "text_hash": ""}

    async def fake_find_summary(database_url, post_id):
        return None

    async def fake_upsert(database_url, **kwargs):
        captured.update(kwargs)

    monkeypatch.setattr(tasks, "fetch_post", fake_fetch_post)
    monkeypatch.setattr(tasks, "find_summary_by_post", fake_find_summary)
    monkeypatch.setattr(tasks, "find_post_by_text_hash", lambda *a, **k: None)
    monkeypatch.setattr(tasks, "upsert_summary", fake_upsert)

    run_async(tasks.summarize_post_logic(5))

    assert captured["summary_text"] == tasks.TECHNICAL_SUMMARY
    assert captured["model"] == "technical"


def test_normal_text_calls_llm(tasks, monkeypatch):
    calls = {}

    async def fake_fetch_post(database_url, post_id):
        return {
            "id": post_id,
            "channel_id": 1,
            "raw_text": "A" * 300,
            "text_hash": "hash123",
            "published_at": "2024-01-01",
        }

    async def fake_find_summary(database_url, post_id):
        return None

    async def fake_find_post_by_hash(database_url, text_hash, exclude_post_id=None):
        return None

    async def fake_upsert(database_url, **kwargs):
        calls["upsert"] = kwargs

    async def fake_summarize(prompt):
        calls["prompt"] = prompt
        return "Краткий дайджест", {"prompt_tokens": 123, "completion_tokens": 45}

    monkeypatch.setattr(tasks, "fetch_post", fake_fetch_post)
    monkeypatch.setattr(tasks, "find_summary_by_post", fake_find_summary)
    monkeypatch.setattr(tasks, "find_post_by_text_hash", fake_find_post_by_hash)
    monkeypatch.setattr(tasks, "upsert_summary", fake_upsert)
    monkeypatch.setattr(tasks.llm_client, "summarize", fake_summarize)

    run_async(tasks.summarize_post_logic(10))

    assert "Краткий дайджест" in calls["upsert"]["summary_text"]
    assert calls["upsert"]["tokens_in"] == 123
    assert calls["upsert"]["tokens_out"] == 45


def test_idempotent_skips_llm(tasks, monkeypatch):
    async def fake_fetch_post(database_url, post_id):
        return {"id": post_id, "channel_id": 1, "raw_text": "A" * 300, "text_hash": "h"}

    async def fake_find_summary(database_url, post_id):
        return {"summary_text": "exists"}

    monkeypatch.setattr(tasks, "fetch_post", fake_fetch_post)
    monkeypatch.setattr(tasks, "find_summary_by_post", fake_find_summary)

    called = False

    async def fake_summarize(prompt):
        nonlocal called
        called = True
        return "", {}

    monkeypatch.setattr(tasks.llm_client, "summarize", fake_summarize)

    run_async(tasks.summarize_post_logic(20))

    assert not called


def test_rate_limit_error_propagates(tasks, monkeypatch):
    async def fake_fetch_post(database_url, post_id):
        return {
            "id": post_id,
            "channel_id": 1,
            "raw_text": "A" * 500,
            "text_hash": "h",
            "published_at": "2024-01-01",
        }

    async def fake_find_summary(database_url, post_id):
        return None

    async def fake_find_post_by_hash(database_url, text_hash, exclude_post_id=None):
        return None

    async def fake_upsert(database_url, **kwargs):
        pass

    async def fake_summarize(prompt):
        response = SimpleNamespace(request=object(), status_code=429, headers={})
        raise tasks.OpenAIRateLimitError("429", response=response, body=None)

    monkeypatch.setattr(tasks, "fetch_post", fake_fetch_post)
    monkeypatch.setattr(tasks, "find_summary_by_post", fake_find_summary)
    monkeypatch.setattr(tasks, "find_post_by_text_hash", fake_find_post_by_hash)
    monkeypatch.setattr(tasks, "upsert_summary", fake_upsert)
    monkeypatch.setattr(tasks.llm_client, "summarize", fake_summarize)

    with pytest.raises(tasks.RateLimitError):
        run_async(tasks.summarize_post_logic(30))
