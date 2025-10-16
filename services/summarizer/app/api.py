from __future__ import annotations

import logging

from fastapi import FastAPI

from .celery_app import celery_app, settings

logging.basicConfig(
    level=settings.log_level.upper(),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
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
    except Exception:
        logging.getLogger(__name__).warning("Failed to inspect celery queues", exc_info=True)
        queues = {}

    return {
        "queues": queues,
        "listening": [settings.queue_summarize, settings.queue_summarize_priority],
    }


@app.on_event("startup")
async def on_startup() -> None:
    logging.getLogger(__name__).info("Summarizer API started")
