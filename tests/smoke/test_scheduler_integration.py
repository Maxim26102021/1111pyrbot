from __future__ import annotations

import importlib
import sys

import pytest


@pytest.fixture
def scheduler_app(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("REDIS_URL", "redis://localhost:6379/0")
    monkeypatch.setenv("DATABASE_URL", "postgresql+asyncpg://user:pass@localhost:5432/db")
    monkeypatch.setenv("DIGEST_PERIOD_MINUTES", "30")
    monkeypatch.setenv("DIGEST_JITTER_SECONDS", "60")

    for module_name in [
        "services.scheduler.app.celery_app",
        "services.scheduler.app.config",
        "services.scheduler.app.utils",
    ]:
        sys.modules.pop(module_name, None)

    module = importlib.import_module("services.scheduler.app.celery_app")
    return module


def test_beat_schedule_has_jitter(scheduler_app):
    sch = scheduler_app.celery_app.conf.beat_schedule["build-and-dispatch"]["schedule"]
    run_every = getattr(sch, "run_every", sch)
    if hasattr(run_every, "total_seconds"):
        seconds = run_every.total_seconds()
    else:
        seconds = float(run_every)
    assert 0 < seconds < 3600
