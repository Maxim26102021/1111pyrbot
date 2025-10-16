from __future__ import annotations

import html
from typing import Iterable, List


def escape_html(text: str) -> str:
    return html.escape(text, quote=False)


def split_message(text: str, max_len: int) -> List[str]:
    if len(text) <= max_len:
        return [text]

    chunks: List[str] = []
    start = 0
    length = len(text)

    while start < length:
        end = min(length, start + max_len)
        split_pos = text.rfind("\n", start, end)
        if split_pos <= start:
            split_pos = text.rfind(" ", start, end)
        if split_pos <= start:
            split_pos = end

        chunk = text[start:split_pos].strip("\n")
        if chunk:
            chunks.append(chunk)

        start = split_pos
        while start < length and text[start] in ("\n", " "):
            start += 1

    return chunks or [text[:max_len]]


def template_digest(title: str, items: Iterable[tuple[str, str]]) -> str:
    title_safe = escape_html(title)
    parts = [f"<b>{title_safe}</b>", ""]
    for channel, summary in items:
        channel_safe = escape_html(channel)
        summary_safe = escape_html(summary)
        parts.append(f"• {channel_safe}: {summary_safe}")
    return "\n".join(parts)
