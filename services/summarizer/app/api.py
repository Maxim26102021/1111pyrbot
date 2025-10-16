from __future__ import annotations

import logging

from fastapi import FastAPI

from libs.core.logging import json_log

from .celery_app import celery_app, settings
from .tasks import METRICS

logger = logging.getLogger(__name__)
SERVICE = "summarizer-api"

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(message)s",
)

app = FastAPI(title="Summarizer Service", version="1.0.0")


@app.get("/health")
async def health() -> dict[str, bool]:
    return {"ok": True}


@app.get("/status")
async def status() -> dict[str, object]:
    queues: dict[str, object] = {}
    try:
        insp = celery_app.control.inspect(timeout=1.0)
        if insp:
            queues = insp.active_queues() or {}
    except Exception as exc:
        json_log(logger, "warning", "celery_inspect_failed", service=SERVICE, error=str(exc))
        queues = {}

    return {
        "queues": queues,
        "listening": [settings.queue_summarize, settings.queue_summarize_priority],
    }


@app.get("/metrics")
async def metrics() -> dict[str, int]:
    return METRICS


@app.on_event("startup")
async def on_startup() -> None:
    json_log(logger, "info", "api_startup", service=SERVICE)
