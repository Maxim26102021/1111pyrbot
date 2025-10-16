from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List

from aiogram import Dispatcher, Router
from aiogram.filters import Command
from aiogram.types import Message

from .celery_app import celery_app, settings
from .dao import (
    fetch_preview_summaries,
    fetch_recent_posts_without_summary,
    upsert_user,
)
from .formatting import template_digest
from .tasks import send_digest

logger = logging.getLogger(__name__)

router = Router()


def register_handlers(dp: Dispatcher, config) -> None:  # config kept for compatibility
    dp.include_router(router)


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    await upsert_user(settings.database_url, message.from_user.id, message.from_user.language_code)
    await message.answer(
        "👋 Привет! Я собираю новости из ваших каналов и присылаю дайджест.\n"
        "Команда /preview_sample покажет пример дайджеста на свежих событиях.",
    )


@router.message(Command("preview_sample"))
async def cmd_preview_sample(message: Message) -> None:
    await upsert_user(settings.database_url, message.from_user.id, message.from_user.language_code)

    awaiting_msg = await message.answer("Готовлю пример, подождите пару секунд…")

    summaries = await fetch_preview_summaries(settings.database_url, limit=settings.preview_sample_limit)

    if not summaries:
        posts = await fetch_recent_posts_without_summary(settings.database_url, limit=settings.preview_sample_limit)
        for post_id in posts:
            celery_app.send_task(
                "summarize_post",
                args=[post_id],
                queue=settings.queue_summarize_priority,
                kwargs={"priority": True},
            )

        for _ in range(5):
            await asyncio.sleep(1.0)
            summaries = await fetch_preview_summaries(settings.database_url, limit=settings.preview_sample_limit)
            if summaries:
                break

    if not summaries:
        await awaiting_msg.edit_text("Пока нет новостей для примера. Попробуйте позже.")
        return

    items = []
    for row in summaries:
        channel_title = row.get("channel_title") or f"Канал {row.get('channel_id')}"
        summary_text = row.get("summary_text") or ""
        items.append((channel_title, summary_text))

    digest_text = template_digest("Ваш дайджест", items)

    send_digest.delay(message.from_user.id, digest_text, parse_mode=settings.telegram_parse_mode)

    await awaiting_msg.edit_text("Отправил пример в личные сообщения 👇")
