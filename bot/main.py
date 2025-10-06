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

bot = Client(
    "/app/sessions/bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

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

# ---------- UTILS ----------
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

async def send_text_in_chunks(chat_id: int, text: str):
    MAX = 4096
    if len(text) <= MAX:
        await bot.send_message(chat_id=chat_id, text=text, disable_web_page_preview=True)
        return
    parts, buf = [], ""
    for para in text.split("\n\n"):
        cand = (buf + ("\n\n" if buf else "") + para)
        if len(cand) > MAX:
            if buf: parts.append(buf)
            buf = para
            while len(buf) > MAX:
                parts.append(buf[:MAX])
                buf = buf[MAX:]
        else:
            buf = cand
    if buf: parts.append(buf)
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

# ---------- HANDLERS ----------
@bot.on_message(filters.command("start") & filters.private)
async def on_start(client, message):
    try:
        upsert_user(message.from_user.id)
        await message.reply_text("👋 Привет! Я собираю новости из ваших каналов и присылаю дайджест 2 раза в день.\n\n" + HELP)
    except Exception:
        logger.exception("Error in /start")
        await message.reply_text("Произошла ошибка. Попробуйте позже.")

@bot.on_message(filters.command("add") & filters.private)
async def on_add(client, message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            return await message.reply_text("Укажи @канал. Пример: /add @neuralnews")
        handle = parts[1]
        subscribe_user_to_channel(message.from_user.id, handle)
        await message.reply_text(f"Добавил {handle}.")
    except Exception:
        logger.exception("Error in /add")
        await message.reply_text("Не удалось добавить канал.")

@bot.on_message(filters.command("list") & filters.private)
async def on_list(client, message):
    try:
        lst = list_user_channels(message.from_user.id)
        if not lst:
            return await message.reply_text("Пусто. Добавь командой /add @канал")
        await message.reply_text("Твои источники:\n" + "\n".join(lst))
    except Exception:
        logger.exception("Error in /list")
        await message.reply_text("Не удалось получить список каналов.")

@bot.on_message(filters.command("remove") & filters.private)
async def on_remove(client, message):
    try:
        parts = message.text.split()
        if len(parts) < 2:
            return await message.reply_text("Укажи @канал. Пример: /remove @neuralnews")
        remove_user_channel(message.from_user.id, parts[1])
        await message.reply_text("Готово.")
    except Exception:
        logger.exception("Error in /remove")
        await message.reply_text("Не удалось удалить канал.")

@bot.on_message(filters.command("when") & filters.private)
async def on_when(client, message):
    try:
        parts = message.text.split()[1:]
        if not parts:
             return await message.reply_text("Укажи время так: /when 09:00 19:30")
        hours = parse_hours(parts)
        if not hours:
            return await message.reply_text("Не удалось распознать время. Пример: /when 09:00 19:30")
        set_user_hours(message.from_user.id, hours)
        await message.reply_text(f"Ок! Часы дайджеста: {', '.join(map(str, hours))}")
    except Exception:
        logger.exception("Error in /when")
        await message.reply_text("Произошла ошибка.")

@bot.on_message(filters.command("digest_now") & filters.private)
async def on_digest_now(client, message):
    try:
        u = get_user_by_tg(message.from_user.id)
        if not u:
            upsert_user(message.from_user.id)
            u = get_user_by_tg(message.from_user.id)
        await message.reply_text("Собираю дайджест за последнее окно...")
        await send_digest_to_user(u)
    except Exception:
        logger.exception("Error in /digest_now")
        await message.reply_text("Не удалось собрать дайджест.")

@bot.on_message(filters.command("plan") & filters.private)
async def on_plan(client, message):
    await message.reply_text("Free: до 5 источников. Pro: до 100 источников и дополнительные окна. Оформить: /buy (пока заглушка)")

@bot.on_message(filters.command("buy") & filters.private)
async def on_buy(client, message):
    try:
        with session_scope() as s:
            s.execute(
                sql("UPDATE users SET plan='pro', valid_until=NOW() + INTERVAL '30 days' WHERE tg_id=:tg"),
                {"tg": message.from_user.id},
            )
        await message.reply_text("Готово! Включил Pro на 30 дней (заглушка).")
    except Exception:
        logger.exception("Error in /buy")
        await message.reply_text("Произошла ошибка.")

@bot.on_message(filters.private)
async def on_private_message(client, message):
    logger.info(f"Caught a non-command private message from {message.from_user.id}: {message.text!r}")
    await message.reply_text("Неизвестная команда. Используйте /start для получения списка команд.")

# ---------- DIGEST & SCHEDULER ----------
async def send_digest_to_user(user):
    user_id = pick(user, "id")
    tg_id = pick(user, "tg_id")
    if not user_id or not tg_id:
        logger.error(f"Invalid user object for digest: {user}")
        return

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

        if not items_list:
            logger.info(f"No new messages for user {user_id} in window {start} - {end}, skipping digest.")
            # Можно отправить сообщение "Нет новостей", если нужно
            # await bot.send_message(tg_id, "За последнее время не было новостей.")
            return

        digest = (build_digest(items_list) or "").strip()
        if not digest or digest == "НЕДОСТАТОЧНО НОВОСТЕЙ":
            logger.info(f"Not enough news to build digest for user {user_id}.")
            return

        save_digest(user_id, start, end, len(items_list), digest, sent_to="user")
        await send_text_in_chunks(chat_id=tg_id, text=digest)
    except Exception:
        logger.exception(f"Error sending digest to user {user_id}")

async def scheduler_tick():
    now = datetime.now(TZ)
    try:
        users = due_users(now.hour, now.minute) or []
        logger.info(f"Scheduler tick: found {len(users)} users due for a digest.")
        for u in users:
            await send_digest_to_user(u)
    except Exception:
        logger.exception("Scheduler tick failed")

# ---------- MAIN LOGIC ----------
def startup_tasks():
    logger.info("Running startup tasks...")
    try:
        run_migrations()
        scheduler.add_job(scheduler_tick, "cron", minute="0,30")
        scheduler.start()
        logger.info("Migrations and scheduler setup complete.")
    except Exception:
        logger.exception("Startup tasks failed!")

if __name__ == "__main__":
    logger.info("Starting bot application...")
    startup_tasks()
    bot.run()

    if scheduler.running:
        scheduler.shutdown()
    logger.info("Bot application stopped.")