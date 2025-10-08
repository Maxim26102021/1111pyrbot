import os, asyncio, pytz, logging
from datetime import datetime, timedelta
from pyrogram import Client
from sqlalchemy import text
from common.db import run_migrations, session_scope
from common.models import add_messages

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

API_ID = int(os.getenv("TELEGRAM_API_ID"))
API_HASH = os.getenv("TELEGRAM_API_HASH")
BOT_TOKEN = os.getenv("BOT_TOKEN")
TZ = pytz.timezone(os.getenv("TZ", "Europe/Amsterdam"))
CYCLE_PAUSE = 300  # 5 минут между проверками

# Создаем клиент для чтения каналов
client = Client(
    "channel_reader",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN,
)

def fetch_channels():
    with session_scope() as s:
        rows = s.execute(text("SELECT id, handle, last_msg_id FROM channels WHERE status='active' ORDER BY id"))
        return [dict(r._mapping) for r in rows]

def update_last_msg_id(channel_id: int, last_id: int):
    with session_scope() as s:
        s.execute(text("UPDATE channels SET last_msg_id=:m, last_checked_at=NOW() WHERE id=:c"), {'m': last_id, 'c': channel_id})

async def fetch_channel_messages(channel):
    """Получение сообщений канала через Telegram API"""
    handle = channel['handle'].lstrip('@')
    last_msg_id = channel.get('last_msg_id', 0)
    
    logger.info(f"Fetching messages from @{handle} (last_msg_id: {last_msg_id})")
    
    try:
        # Получаем информацию о канале
        chat = await client.get_chat(f"@{handle}")
        if not chat:
            logger.error(f"Could not access channel @{handle}")
            return []
            
        messages = []
        
        # Получаем последние сообщения из канала
        # Используем get_messages вместо get_chat_history
        try:
            # Пытаемся получить сообщения начиная с последнего известного ID
            start_id = last_msg_id + 1 if last_msg_id > 0 else 1
            end_id = start_id + 50  # Получаем до 50 сообщений
            
            # Получаем сообщения по ID
            for msg_id in range(start_id, end_id):
                try:
                    message = await client.get_messages(chat.id, msg_id)
                    if message and message.text:
                        # Создаем ссылку на сообщение
                        link = f"https://t.me/{handle}/{message.id}"
                        
                        # Конвертируем дату в нужный часовой пояс
                        msg_date = message.date.astimezone(TZ)
                        
                        messages.append({
                            'channel_id': channel['id'],
                            'tg_message_id': message.id,
                            'msg_date': msg_date,
                            'link': link,
                            'text': message.text
                        })
                except Exception:
                    # Если сообщение не найдено, пропускаем
                    continue
                    
        except Exception as e:
            logger.warning(f"Could not fetch messages by ID from @{handle}: {e}")
            # Fallback: попробуем получить последние сообщения другим способом
            try:
                # Получаем последние сообщения через get_messages без указания ID
                recent_messages = await client.get_messages(chat.id, limit=20)
                for message in recent_messages:
                    if message and message.id > last_msg_id and message.text:
                        # Создаем ссылку на сообщение
                        link = f"https://t.me/{handle}/{message.id}"
                        
                        # Конвертируем дату в нужный часовой пояс
                        msg_date = message.date.astimezone(TZ)
                        
                        messages.append({
                            'channel_id': channel['id'],
                            'tg_message_id': message.id,
                            'msg_date': msg_date,
                            'link': link,
                            'text': message.text
                        })
            except Exception as e2:
                logger.error(f"Fallback method also failed for @{handle}: {e2}")
                return []
            
        logger.info(f"Found {len(messages)} new messages from @{handle}")
        return messages
        
    except Exception as e:
        logger.error(f"Error fetching messages from @{handle}: {e}")
        return []

async def main():
    run_migrations()

    logger.info("Reader service started with Telegram API")

    async with client:
        while True:
            channels = fetch_channels()
            logger.info(f"Found {len(channels)} active channels to poll")

            if not channels:
                logger.info("No channels to poll. Sleeping...")
                await asyncio.sleep(CYCLE_PAUSE)
                continue

            all_messages = []

            for ch in channels:
                # Используем Telegram API для получения сообщений
                messages = await fetch_channel_messages(ch)
                if messages:
                    all_messages.extend(messages)
                    logger.info(f"Fetched {len(messages)} messages from @{ch['handle']}")
                    
                    # Обновляем last_msg_id для канала
                    if messages:
                        latest_id = max(msg['tg_message_id'] for msg in messages)
                        update_last_msg_id(ch['id'], latest_id)

            if all_messages:
                # Сохраняем все сообщения в базу данных
                add_messages(all_messages)
                logger.info(f"Saved {len(all_messages)} messages to database")

            logger.info(f"Completed fetching cycle. Sleeping for {CYCLE_PAUSE}s...")
            await asyncio.sleep(CYCLE_PAUSE)

if __name__ == "__main__":
    asyncio.run(main())
