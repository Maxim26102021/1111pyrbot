from __future__ import annotations

import asyncio
import logging
from typing import Optional

from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.exceptions import TelegramForbiddenError, TelegramNetworkError, TelegramRetryAfter

from libs.core.logging import json_log
from .config import load_settings
from .formatting import split_message

logger = logging.getLogger(__name__)
SERVICE = "bot"

settings = load_settings()

bot = Bot(
    token=settings.bot_token,
    default=DefaultBotProperties(parse_mode=settings.telegram_parse_mode),
)

MAX_RETRIES = 3

METRICS = {
    "messages_sent": 0,
    "flood_waits": 0,
    "fatal_errors": 0,
}

class RetryableTelegramError(Exception):
    def __init__(self, delay: Optional[float] = None) -> None:
        super().__init__(f"Retry after {delay}s" if delay else "Retryable Telegram error")
        self.delay = delay


class FatalTelegramError(Exception):
    pass


async def _send_chunk(tg_user_id: int, text: str, parse_mode: str | None) -> None:
    await bot.send_message(
        chat_id=tg_user_id,
        text=text,
        disable_web_page_preview=True,
        parse_mode=parse_mode,
    )


async def send_text(tg_user_id: int, text: str, parse_mode: str | None = None) -> int:
    chunks = split_message(text, settings.telegram_max_message)
    sent = 0

    for chunk in chunks:
        attempt = 0
        while True:
            try:
                await _send_chunk(tg_user_id, chunk, parse_mode)
                sent += 1
                break
            except TelegramRetryAfter as exc:
                attempt += 1
                delay = exc.retry_after if settings.telegram_sleep_on_flood == "auto" else float(settings.telegram_sleep_on_flood)
                if attempt > MAX_RETRIES:
                    raise RetryableTelegramError(delay) from exc
                METRICS["flood_waits"] += 1
                json_log(logger, "warning", "flood_wait", service=SERVICE, user_id=tg_user_id, delay=delay)
                await asyncio.sleep(delay)
            except TelegramNetworkError as exc:
                attempt += 1
                if attempt > MAX_RETRIES:
                    raise RetryableTelegramError() from exc
                await asyncio.sleep(2 * attempt)
            except TelegramForbiddenError as exc:
                METRICS["fatal_errors"] += 1
                raise FatalTelegramError(str(exc)) from exc
    METRICS["messages_sent"] += sent
    return sent
