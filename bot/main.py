cat > bot/main.py << 'PY'
import os
import sys
import asyncio
import logging
from datetime import datetime, timedelta

import pytz
from pyrogram import Client, filters, idle
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

# ---------- ENV ----------
BOT_TOKEN = os.getenv("BOT_TOKEN")
API_ID = os.getenv("TELEGRAM_API_ID")
API_HASH = os.getenv("TELEGRAM_API_HASH")
if not BOT_TOKEN:
    raise RuntimeError("BOT_TOKEN is not set")
if not API_ID or not API_HASH:
    raise RuntimeError("TELEGRAM_API_ID / TELEGRAM_API_HASH are not set")
API_ID = int(API_ID)

TZ = pytz.timezone(os.getenv("TZ", "Europe/Amsterdam"))

# Чистая in-memory сессия: исключает конфликты со старыми *.session
bot = Client(
    "promteo_release_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
    in_memory=True,
)

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

# ---------- HANDLERS ----------
@bot.on_message(filters.command("start") & filters.private, group=0)
async def on_start(_, m):
    try:
        upsert_user(m.from_user.id)
        await m.reply_text("👋 Привет! Я собираю новости из твоих каналов и присылаю дайджест 2 раза в день.\n\n" + HELP)
    except Exception:
        logger.exception("Error in /start")
        try: await m.reply_text("Произошла ошибка при запуске. Попробуй позже.")
        except Exception: pass

@bot.on_message(filters.command("add") & filters.private, group=0)
async def on_add(_, m):
    try:
        if not (m.text and m.text.strip()):
            return await m.reply_text("Нужно прислать текст команды. Пример: /add @neuralnews")
        parts = m.text.split()
        if len(parts) < 2:
            return await m.reply_text("Укажи @канал. Пример: /add @neuralnews")
        handle = parts[1]
        subscribe_user_to_channel(m.from_user.id, handle)
        await m.reply_text(f"Добавил {handle}. Публичные — читаю сразу. Приватные — только при доступе.")
    except Exception:
        logger.exception("Error in /add")
        try: await m.reply_text("Не удалось добавить канал. Попробуй позже.")
        except Exception: pass

@bot.on_message(filters.command("list") & filters.private, group=0)
async def on_list(_, m):
    try:
        lst = list_user_channels(m.from_user.id)
        if not lst:
            return await m.reply_text("Пусто. Добавь командой /add @канал")
        await m.reply_text("Твои источники:\n" + "\n".join(lst))
    except Exception:
        logger.exception("Error in /list")
        try: await m.reply_text("Не удалось получить список каналов.")
        except Exception: pass

@bot.on_message(filters.command("remove") & filters.private, group=0)
async def on_remove(_, m):
    try:
        if not (m.text and m.text.strip()):
            return await m.reply_text("Нужно прислать текст команды. Пример: /remove @neuralnews")
        parts = m.text.split()
        if len(parts) < 2:
            return await m.reply_text("Укажи @канал. Пример: /remove @neuralnews")
        remove_user_channel(m.from_user.id, parts[1])
        await m.reply_text("Готово.")
    except Exception:
        logger.exception("Error in /remove")
        try: await m.reply_text("Не удалось удалить канал.")
        except Exception: pass

@bot.on_message(filters.command("when") & filters.private, group=0)
async def on_when(_, m):
    try:
        parts = (m.text.split()[1:] if (m.text and m.text.strip()) else [])
        hours = parse_hours(parts)
        if not hours:
            return await m.reply_text("Укажи время так: /when 09:00 19:30")
        set_user_hours(m.from_user.id, hours)
        await m.reply_text(f"Ок! Часы дайджеста: {', '.join(map(str, hours))}")
    except Exception:
        logger.exception("Error in /when")
        try: await m.reply_text("Произошла ошибка. Попробуй позже.")
        except Exception: pass

@bot.on_message(filters.command("plan") & filters.private, group=0)
async def on_plan(_, m):
    try:
        await m.reply_text("Free: до 5 источников. Pro: до 100 источников и дополнительные окна. Оформить: /buy (пока заглушка)")
    except Exception:
        logger.exception("Error in /plan")
        try: await m.reply_text("Произошла ошибка. Попробуй позже.")
        except Exception: pass

@bot.on_message(filters.command("buy") & filters.private, group=0)
async def on_buy(_, m):
    try:
        with session_scope() as s:
            s.execute(
                sql("UPDATE users SET plan='pro', valid_until=NOW() + INTERVAL '30 days' WHERE tg_id=:tg"),
                {"tg": m.from_user.id},
            )
        await m.reply_text("Готово! Включил Pro на 30 дней (заглушка).")
    except Exception:
        logger.exception("Error in /buy")
        try: await m.reply_text("Произошла ошибка. Попробуй позже.")
        except Exception: pass

@bot.on_message(filters.command("digest_now") & filters.private, group=0)
async def on_digest_now(_, m):
    try:
        u = get_user_by_tg(m.from_user.id)
        if not u:
            upsert_user(m.from_user.id)
            u = get_user_by_tg(m.from_user.id)
        await send_digest_to_user(u)
        await m.reply_text("Отправил дайджест (если набралось новостей).")
    except Exception as e:
        logger.exception("Error in /digest_now")
        try: await m.reply_text(f"Ошибка: {e}")
        except Exception: pass

@bot.on_message(filters.private, group=1)
async def catch_all_messages(_, message):
    try:
        logger.info(f"Non-command message from {message.from_user.id}: {getattr(message, 'text', None)!r}")
    except Exception:
        logger.exception("Error in catch_all_messages")

# ---------- DIGEST ----------
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

# ---------- SCHEDULER ----------
async def scheduler_tick():
    now = datetime.now(TZ)
    try:
        users = due_users(now.hour, now.minute) or []
        for u in users:
            await send_digest_to_user(u)
    except Exception:
        logger.exception("Scheduler tick failed")

# ---------- MAIN ----------
async def main():
    masked = BOT_TOKEN[:8] + "…"
    logger.info(f"ENV check: BOT_TOKEN={bool(BOT_TOKEN)}({masked}) API_ID={bool(API_ID)} API_HASH={bool(API_HASH)} TZ={TZ}")
    await bot.start()
    me = await bot.get_me()
    logger.info(f"Logged as @{getattr(me,'username',None)} (id={me.id}), is_bot={getattr(me,'is_bot',None)}")
    if not getattr(me, "is_bot", False):
        logger.critical("is_bot=False → проверь BOT_TOKEN")
        await bot.stop()
        sys.exit(1)

    loop = asyncio.get_running_loop()
    try:
        await loop.run_in_executor(None, run_migrations)
    except Exception:
        logger.exception("Migrations failed — продолжу работать")

    scheduler = AsyncIOScheduler(timezone=str(TZ))
    scheduler.add_job(scheduler_tick, "cron", minute="0,30")
    scheduler.start()
    logger.info("Scheduler started. Waiting for updates…")

    await idle()

    logger.info("Stopping…")
    scheduler.shutdown(wait=False)
    await bot.stop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception:
        logger.exception("Fatal error in main()")
        sys.exit(1)
PY
