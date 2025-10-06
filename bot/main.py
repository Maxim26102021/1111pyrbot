import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta

import pytz
from pyrogram import Client, filters
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import text as sql

from common.db import run_migrations, session_scope
from common.models import (
    upsert_user, get_user_by_tg, set_user_hours,
    subscribe_user_to_channel, list_user_channels, remove_user_channel,
    due_users, get_user_window_messages, save_digest
)
from common.summarize import build_digest

# ---------- LOGGING ----------
logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    force=True,
)
logger = logging.getLogger("promteo_bot")

# ---------- ENV & CLIENT SETUP ----------
try:
    BOT_TOKEN = os.getenv("BOT_TOKEN")
    API_ID = int(os.getenv("TELEGRAM_API_ID"))
    API_HASH = os.getenv("TELEGRAM_API_HASH")
    if not all([BOT_TOKEN, API_ID, API_HASH]):
        raise ValueError("One of the required env variables is missing")
    TZ = pytz.timezone(os.getenv("TZ", "Europe/Amsterdam"))
except (ValueError, TypeError) as e:
    logger.critical(f"FATAL: Env variables are not configured correctly. Error: {e}")
    sys.exit(1)

# Используем файловую сессию
bot = Client(
    "/app/sessions/bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

# Инициализируем планировщик
scheduler = AsyncIOScheduler(timezone=str(TZ))

HELP = (
    "Команды:\n"
    "/start — начать\n"
    "/add @канал — добавить источник\n"
    "/list — список источников\n"
    "/remove @канал — удалить источник\n"
    "/when HH:MM HH:MM — время дайджестов\n"
    "/digest_now — прислать дайджест за последнее окно\n"
    "/plan — тарифы\n"
    "/buy — оформить Pro (заглушка)\n"
)

# ---------- UTILS (без изменений) ----------
def parse_hours(args):
    hours = []
    for t in args:
        try:
            h, _ = t.split(":")
            h = int(h)
            if 0 <= h <= 23:
                hours.append(h)
        except Exception:
            continue
    return sorted(set(hours))

def pick(obj, key, default=None):
    try:
        return getattr(obj, key)
    except Exception:
        try:
            return obj[key]
        except Exception:
            return default

# ... (остальные утилиты без изменений) ...
async def send_text_in_chunks(chat_id: int, text: str):
    MAX = 4096
    if len(text) <= MAX:
        await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
        return
    parts, buf = [], ""
    for para in text.split("\n\n"):
        cand = (buf + ("\n\n" if buf else "") + para)
        if len(cand) > MAX:
            if buf:
                parts.append(buf); buf = para
                if len(buf) > MAX:
                    while len(buf) > MAX:
                        parts.append(buf[:MAX]); buf = buf[MAX:]
            else:
                p = para
                while len(p) > MAX:
                    parts.append(p[:MAX]); p = p[MAX:]
                buf = p
        else:
            buf = cand
    if buf:
        parts.append(buf)
    for p in parts:
        await bot.send_message(chat_id=chat_id, text=p, disable_web_page_preview=True)

def window_for_now(now: datetime):
    h = now.hour
    if h < 12:
        start = (now - timedelta(hours=12)).replace(minute=0, second=0, microsecond=0)
        end = now.replace(minute=0, second=0, microsecond=0)
    else:
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(minute=0, second=0, microsecond=0)
    return start, end


# ---------- HANDLERS (без изменений) ----------
@bot.on_message(filters.command("start") & filters.private, group=0)
async def on_start(_, m):
    try:
        upsert_user(m.from_user.id)
        await m.reply_text("👋 Привет! Я собираю новости из твоих каналов и присылаю дайджест 2 раза в день.\n\n" + HELP)
    except Exception:
        logger.exception("Error in /start")
        try: await m.reply_text("Произошла ошибка при запуске. Попробуй позже.")
        except Exception: pass

@bot.on_message(filters.private, group=1)
async def catch_all_messages(_, message):
    logger.info(f"Non-command message from {message.from_user.id}: {getattr(message, 'text', None)!r}")


# === DEBUG: логируем вообще все входящие сообщения ===
@bot.on_message(group=-1)
async def __debug_all_updates(_, m):
    try:
        logger.info(f"[DEBUG] update: chat_type={getattr(m.chat, 'type', None)} from={getattr(m.from_user, 'id', None)} text={getattr(m,'text',None)!r}")
    except Exception:
        logger.exception("debug logger failed")


# ---------- DIGEST & SCHEDULER (без изменений) ----------
async def send_digest_to_user(user):
    user_id = pick(user, "id")
    tg_id = pick(user, "tg_id")
    now = datetime.now(TZ)
    start, end = window_for_now(now)
    try:
        items = get_user_window_messages(user_id, start, end) or []
        uniq = {}
        for it in items:
            key = it.get("text_hash")
            if key and key not in uniq:
                uniq[key] = {"text": it.get("text"), "link": it.get("link")}
        items_list = list(uniq.values())
        digest = (build_digest(items_list) or "").strip()
        if not digest or digest == "НЕДОСТАТОЧНО НОВОСТЕЙ":
            return
        save_digest(user_id, start, end, len(items_list), digest, sent_to="user")
        await send_text_in_chunks(chat_id=tg_id, text=digest)
    except Exception:
        logger.exception(f"Error sending digest to user {user_id}")

async def scheduler_tick():
    now = datetime.now(TZ)
    try:
        users = due_users(now.hour, now.minute) or []
        for u in users:
            await send_digest_to_user(u)
    except Exception:
        logger.exception("Scheduler tick failed")


# ---------- MAIN LOGIC ----------
def startup_tasks():
    # Эта функция будет выполняться ДО запуска Pyrogram
    logger.info("Running startup tasks...")
    try:
        run_migrations()
        scheduler.add_job(scheduler_tick, "cron", minute="0,30")
        scheduler.start()
        logger.info("Migrations and scheduler setup complete.")
    except Exception:
        logger.exception("Startup tasks failed!")
        # Можно завершить процесс, если миграции критичны
        # sys.exit(1)

if __name__ == "__main__":
    logger.info("Starting bot application...")
    # 1. Выполняем синхронные задачи подготовки
    startup_tasks()

    # 2. Запускаем бота через bot.run().
    # Этот метод сам управляет циклом, запуском, остановкой по SIGTERM.
    # Это решает проблему "attached to a different loop".
    bot.run()

    # После остановки бота (например, по Ctrl+C)
    if scheduler.running:
        scheduler.shutdown()
    logger.info("Bot application stopped.")