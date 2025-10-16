from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping, MutableMapping, Sequence


@dataclass(slots=True)
class PostDTO:
    post_id: int
    channel_id: int
    channel_title: str | None
    message_id: int
    text: str
    published_at: datetime
    entities: Sequence[Mapping[str, Any]] | None = None


@dataclass(slots=True)
class SummaryDTO:
    post_id: int
    summary: str
    model: str
    tokens_in: int
    tokens_out: int
    cost: float
    created_at: datetime
