from __future__ import annotations

import logging

from celery import Celery

logger = logging.getLogger(__name__)


def create_celery_app(broker_url: str, backend_url: str) -> Celery:
    app = Celery("digest", broker=broker_url, backend=backend_url)
    return app


class TaskQueue:
    def __init__(self, app: Celery, summarize_queue: str) -> None:
        self._app = app
        self._summarize_queue = summarize_queue

    def send_summarize_task(self, post_id: int) -> None:
        logger.info("Queueing summarize_post task", extra={"post_id": post_id, "queue": self._summarize_queue})
        self._app.send_task(
            "summarize_post",
            args=[post_id],
            queue=self._summarize_queue,
        )
