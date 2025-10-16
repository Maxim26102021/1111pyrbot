from __future__ import annotations

import random
from hashlib import sha256


def hash_text(text: str) -> str:
    """Return a stable hash for caching text content."""
    return sha256(text.encode("utf-8")).hexdigest()


def next_backoff(
    attempt: int,
    *,
    base: float = 1.0,
    factor: float = 2.0,
    jitter: float = 0.2,
    maximum: float = 60.0,
) -> float:
    """Exponential backoff with jitter."""
    delay = base * (factor ** max(attempt - 1, 0))
    delay = min(delay, maximum)
    if jitter:
        delay *= random.uniform(1 - jitter, 1 + jitter)
    return delay
