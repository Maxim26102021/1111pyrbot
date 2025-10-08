import os, asyncio, pytz, logging
from datetime import datetime
from pyrogram import Client
from pyrogram.errors import FloodWait, RPCError, AuthKeyInvalid, SessionPasswordNeeded
from sqlalchemy import text
from common.db import run_migrations, session_scope
from common.models import add_messages

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")  # Используем токен бота для авторизации
SESSION_NAME = os.getenv("TELEGRAM_SESSION_NAME", "service1")
SESSIONS_DIR = "/app/sessions"
POLL_LIMIT = 200
SLEEP_BETWEEN_CHANNELS = 2
CYCLE_PAUSE = 60
TZ = pytz.timezone(os.getenv("TZ", "Europe/Amsterdam"))

def fetch_channels():
    with session_scope() as s:
        rows = s.execute(text("SELECT id, handle, last_msg_id FROM channels WHERE status='active' ORDER BY id"))
        return [dict(r._mapping) for r in rows]

def update_last_msg_id(channel_id: int, last_id: int):
    with session_scope() as s:
        s.execute(text("UPDATE channels SET last_msg_id=:m, last_checked_at=NOW() WHERE id=:c"), {'m': last_id, 'c': channel_id})

async def poll_channel(app: Client, channel):
    handle = channel['handle']
    print(f"[reader] Polling @{handle} from last_msg_id={channel['last_msg_id']}")
    try:
        chat = await app.get_chat(handle)
    except RPCError as e:
        print(f"[reader] can't get chat @{handle}: {e}")
        return

    new_items = []
    max_id = channel['last_msg_id'] or 0
    try:
        async for m in app.get_chat_history(chat.id, limit=POLL_LIMIT):
            if m.id <= (channel['last_msg_id'] or 0):
                break
            text_content = m.text or m.caption
            if not text_content:
                continue
            msg_dt = m.date.astimezone(pytz.UTC).astimezone(TZ)
            link = f"https://t.me/{chat.username}/{m.id}" if chat.username else None
            new_items.append({
                'channel_id': channel['id'],
                'tg_message_id': m.id,
                'msg_date': msg_dt,
                'link': link,
                'text': text_content
            })
            if m.id > max_id:
                max_id = m.id
        if new_items:
            new_items.sort(key=lambda x: x['tg_message_id'])
            add_messages(new_items)
            update_last_msg_id(channel['id'], max_id)
            print(f"[reader] @{handle}: +{len(new_items)} new (last_id={max_id})")
    except FloodWait as e:
        print(f"[reader] FLOOD_WAIT for @{handle}: sleep {e.value}s")
        await asyncio.sleep(e.value)
    except RPCError as e:
        print(f"[reader] RPC error on @{handle}: {e}")
    await asyncio.sleep(SLEEP_BETWEEN_CHANNELS)

async def main():
    run_migrations()

    # Проверяем наличие bot token
    if not BOT_TOKEN:
        logger.error("BOT_TOKEN не найден в переменных окружения")
        return

    # Используем bot token для авторизации
    app = Client(
        "bot_reader",
        api_id=API_ID,
        api_hash=API_HASH,
        bot_token=BOT_TOKEN,
        workdir=SESSIONS_DIR
    )

    try:
        async with app:
            logger.info("Reader service started successfully with bot token")
            me = await app.get_me()
            logger.info(f"Authorized as: @{me.username}")

            while True:
                channels = fetch_channels()
                logger.info(f"Found {len(channels)} active channels to poll")

                if not channels:
                    logger.info("No channels to poll. Sleeping...")
                    await asyncio.sleep(CYCLE_PAUSE)
                    continue

                for ch in channels:
                    await poll_channel(app, ch)

                logger.info(f"Completed polling cycle. Sleeping for {CYCLE_PAUSE}s...")
                await asyncio.sleep(CYCLE_PAUSE)

    except Exception as e:
        logger.error(f"Error in main loop: {e}")
        raise

if __name__ == "__main__":
    asyncio.run(main())
