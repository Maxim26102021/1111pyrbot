from __future__ import annotations

import random
from datetime import timedelta
from typing import Iterable, List, Tuple


def add_jitter(base: timedelta, jitter_seconds: int) -> timedelta:
    if jitter_seconds <= 0:
        return base
    shift = random.uniform(-jitter_seconds, jitter_seconds)
    return base + timedelta(seconds=shift)


def format_digest(summaries: Iterable[Tuple[int, int, str]]) -> str:
    points: List[str] = []
    for idx, item in enumerate(summaries):
        if idx >= 10:
            break
        post_id, channel_id, summary_text = item[:3]
        summary_text = (summary_text or "").strip()
        if not summary_text:
            continue
        points.append(f"• Канал {channel_id}: {summary_text}")
    return "\n".join(points)
