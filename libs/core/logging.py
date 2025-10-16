from __future__ import annotations

import json
import logging
from typing import Any


def json_log(logger: logging.Logger, level: str, event: str, **fields: Any) -> None:
    payload = {"event": event}
    payload.update({k: v for k, v in fields.items() if v is not None})
    message = json.dumps(payload, ensure_ascii=False)
    log_fn = getattr(logger, level.lower(), logger.info)
    log_fn(message)
