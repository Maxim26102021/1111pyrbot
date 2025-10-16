from __future__ import annotations

import importlib
import sys

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def api_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    for module_name in [
        "services.summarizer.app.api",
        "services.summarizer.app.celery_app",
        "services.summarizer.app.config",
    ]:
        sys.modules.pop(module_name, None)

    api_module = importlib.import_module("services.summarizer.app.api")
    return api_module.app


def test_health_endpoint(api_app):
    client = TestClient(api_app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
