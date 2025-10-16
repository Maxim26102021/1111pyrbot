from __future__ import annotations

import logging
import os

from services.ingest.app.worker import main as worker_main


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


if __name__ == "__main__":
    configure_logging(os.getenv("LOG_LEVEL", "INFO"))
    worker_main()
