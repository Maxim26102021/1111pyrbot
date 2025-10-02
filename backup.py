import os
import pytz
import asyncio
import logging
from datetime import datetime, timedelta

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

# 1. НАСТРОЙКА ЛОГИРОВАНИЯ
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# 2. ЗАГРУЗКА ПЕРЕМЕННЫХ ОКРУЖЕНИЯ
BOT_TOKEN = os.getenv('BOT_TOKEN')
TZ = pytz.timezone(os.getenv('TZ', 'Europe/Amsterdam'))
API_ID = int(os.getenv('TELEGRAM_API_ID'))
API_HASH = os.getenv('TELEGRAM_API_HASH')

# 3. ИНИЦИАЛИЗАЦИЯ КЛИЕНТА PYROGRAM
bot = Client('promteo_bot', api_id=API_ID, api_hash=API_HASH, bot_token=BOT_TOKEN)

HELP = (
    """Команды:
    /start — начать
    /add @канал — добавить источник
    /list — список источников
    /remove @канал — удалить источник
    /when HH:MM HH:MM — время дайджестов (часы из времени попадут в расписание)
    /digest_now — прислать дайджест за последнее окно (тест)
    /plan — тарифы
    /buy — оформить Pro (заглушка)
    """
)

def parse_hours(args):
    hours = []
    for t in args:
        try:
            h, m = t.split(':')
            hours.append(int(h))
        except:
            continue
    return sorted(list(set([h for h in hours if 0 <= h <= 23])))

# --- ОБРАБОТЧИКИ КОМАНД (СНАЧАЛА КОНКРЕТНЫЕ) ---

@bot.on_message(filters.command('start') & filters.private)
async def on_start(_, m):
    try:
        upsert_user(m.from_user.id)
        await m.reply_text(
            "👋 Привет! Я собираю новости из ваших каналов и присылаю дайджест 2 раза в день.\n\n" + HELP
        )
    except Exception as e:
        logger.error(f"Error in /start handler for user {m.from_user.id}: {e}")
        await m.reply_text("Произошла ошибка при запуске. Попробуйте позже.")

@bot.on_message(filters.command('add') & filters.private)
async def on_add(_, m):
    try:
        parts = m.text.split()
        if len(parts) < 2:
            return await m.reply_text("Укажи @канал. Пример: /add @neuralnews")
        handle = parts[1]
        subscribe_user_to_channel(m.from_user.id, handle)
        await m.reply_text(f"Добавил {handle}. Публичные — читаю сразу. Приватные — только при доступе.")
    except Exception as e:
        logger.error(f"Error in /add handler for user {m.from_user.id}: {e}")
        await m.reply_text("Не удалось добавить канал. Попробуйте позже.")

@bot.on_message(filters.command('list') & filters.private)
async def on_list(_, m):
    try:
        lst = list_user_channels(m.from_user.id)
        if not lst:
            return await m.reply_text("Пусто. Добавь командой /add @канал")
        await m.reply_text("Твои источники:\n" + "\n".join(lst))
    except Exception as e:
        logger.error(f"Error in /list handler for user {m.from_user.id}: {e}")
        await m.reply_text("Не удалось получить список каналов.")

@bot.on_message(filters.command('remove') & filters.private)
async def on_remove(_, m):
    try:
        parts = m.text.split()
        if len(parts) < 2:
            return await m.reply_text("Укажи @канал. Пример: /remove @neuralnews")
        remove_user_channel(m.from_user.id, parts[1])
        await m.reply_text("Готово.")
    except Exception as e:
        logger.error(f"Error in /remove handler for user {m.from_user.id}: {e}")
        await m.reply_text("Не удалось удалить канал.")

@bot.on_message(filters.command('when') & filters.private)
async def on_when(_, m):
    try:
        parts = m.text.split()[1:]
        hours = parse_hours(parts)
        if not hours:
            return await m.reply_text("Укажи время так: /when 09:00 19:30")
        set_user_hours(m.from_user.id, hours)
        await m.reply_text(f"Ок! Часы дайджеста: {', '.join(map(str, hours))}")
    except Exception as e:
        logger.error(f"Error in /when handler for user {m.from_user.id}: {e}")
        await m.reply_text("Произошла ошибка. Попробуйте позже.")

@bot.on_message(filters.command('plan') & filters.private)
async def on_plan(_, m):
    try:
        await m.reply_text("Free: до 5 источников. Pro: до 100 источников и дополнительные окна. Оформить: /buy (пока заглушка)")
    except Exception as e:
        logger.error(f"Error in /plan handler for user {m.from_user.id}: {e}")
        await m.reply_text("Произошла ошибка. Попробуйте позже.")

@bot.on_message(filters.command('buy') & filters.private)
async def on_buy(_, m):
    try:
        with session_scope() as s:
            s.execute(sql("""UPDATE users SET plan='pro', valid_until=NOW() + INTERVAL '30 days' WHERE tg_id=:tg"""), {'tg': m.from_user.id})
        await m.reply_text("Готово! Включил Pro на 30 дней (заглушка).")
    except Exception as e:
        logger.error(f"Error in /buy handler for user {m.from_user.id}: {e}")
        await m.reply_text("Произошла ошибка. Попробуйте позже.")

@bot.on_message(filters.command('digest_now') & filters.private)
async def on_digest_now(_, m):
    try:
        u = get_user_by_tg(m.from_user.id)
        if not u:
            upsert_user(m.from_user.id)
            u = get_user_by_tg(m.from_user.id)
        await send_digest_to_user(u)
        await m.reply_text("Отправил дайджест (если набралось новостей).")
    except Exception as e:
        logger.error(f"Error in /digest_now handler for user {m.from_user.id}: {e}")
        await m.reply_text(f"Ошибка: {e}")

# --- ОБЩИЙ ОБРАБОТЧИК (В САМОМ КОНЦЕ, ЧТОБЫ НЕ МЕШАТЬ ДРУГИМ) ---
@bot.on_message(filters.private)
async def catch_all_messages(_, message):
    logger.info(f"!!! ПОЙМАЛ СООБЩЕНИЕ (не команда): '{message.text}' от пользователя {message.from_user.id} !!!")
    # Можно добавить ответ, если нужно, например:
    # await message.reply_text("Я не понял команду. Используйте /start для помощи.")

def window_for_now(now: datetime):
    h = now.hour
    if h < 12:
        start = (now - timedelta(hours=12)).replace(minute=0, second=0, microsecond=0)
        end = now.replace(minute=0, second=0, microsecond=0)
    else:
        start = now.replace(hour=9, minute=0, second=0, microsecond=0)
        end = now.replace(minute=0, second=0, microsecond=0)
    return start, end

async def send_digest_to_user(user):
    user_id = user['id']
    now = datetime.now(TZ)
    start, end = window_for_now(now)
    try:
        items = get_user_window_messages(user_id, start, end)
        uniq = {}
        for it in items:
            key = it.get('text_hash')
            if key not in uniq:
                uniq[key] = {'text': it.get('text'), 'link': it.get('link')}
        items_list = list(uniq.values())
        digest = build_digest(items_list)
        if digest.strip() == 'НЕДОСТАТОЧНО НОВОСТЕЙ':
            return
        save_digest(user_id, start, end, len(items_list), digest, sent_to='user')
        await bot.send_message(chat_id=user['tg_id'], text=digest, disable_web_page_preview=True)
    except Exception as e:
        logger.error(f"Error sending digest to user {user_id}: {e}")

async def scheduler_tick():
    now = datetime.now(TZ)
    try:
        users = due_users(now.hour, now.minute)
        for u in users:
            await send_digest_to_user(u)
    except Exception as e:
        logger.error(f"Scheduler tick failed: {e}")

# --- ГЛАВНАЯ ФУНКЦИЯ ЗАПУСКА ---
async def main():
    async with bot:
        run_migrations()
        scheduler = AsyncIOScheduler(timezone=str(TZ))
        scheduler.add_job(scheduler_tick, 'cron', minute='0,30')
        scheduler.start()
        logger.info("Bot up and running, scheduler started.")
        await asyncio.Event().wait()

# --- ТОЧКА ВХОДА В ПРОГРАММУ ---
if __name__ == '__main__':
    logger.info("Starting bot...")
    asyncio.run(main())
