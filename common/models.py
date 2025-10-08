from sqlalchemy import text
from .db import session_scope

def upsert_user(tg_id: int):
    with session_scope() as s:
        res = s.execute(text("""
            INSERT INTO users (tg_id) VALUES (:tg_id)
            ON CONFLICT (tg_id) DO UPDATE SET tg_id = EXCLUDED.tg_id
            RETURNING id, plan, tz, digest_hours
        """), {'tg_id': tg_id}).mappings().first()
        return res

def get_user_by_tg(tg_id: int):
    with session_scope() as s:
        res = s.execute(text("""SELECT * FROM users WHERE tg_id=:tg_id"""), {'tg_id': tg_id}).mappings().first()
        return res

def set_user_hours(tg_id: int, hours):
    with session_scope() as s:
        s.execute(text("""UPDATE users SET digest_hours=:h WHERE tg_id=:tg_id"""), {'h': hours, 'tg_id': tg_id})

def ensure_channel(handle: str):
    handle = handle.lstrip('@')
    with session_scope() as s:
        res = s.execute(text("""
            INSERT INTO channels (handle, status) VALUES (:h, 'active')
            ON CONFLICT (handle) DO UPDATE SET status='active'
            RETURNING id, handle
        """), {'h': handle}).mappings().first()
        return res

def subscribe_user_to_channel(tg_id: int, handle: str):
    ch = ensure_channel(handle)
    with session_scope() as s:
        uid = s.execute(text("""SELECT id FROM users WHERE tg_id=:tg"""), {'tg': tg_id}).scalar()
        s.execute(text("""
            INSERT INTO subscriptions (user_id, channel_id) VALUES (:u, :c)
            ON CONFLICT DO NOTHING
        """), {'u': uid, 'c': ch['id']})

def list_user_channels(tg_id: int):
    with session_scope() as s:
        res = s.execute(text("""
            SELECT c.handle FROM subscriptions s
            JOIN users u ON u.id=s.user_id
            JOIN channels c ON c.id=s.channel_id
            WHERE u.tg_id=:tg
            ORDER BY c.handle
        """), {'tg': tg_id}).scalars().all()
        return ['@'+h for h in res]

def remove_user_channel(tg_id: int, handle: str):
    handle = handle.lstrip('@')
    with session_scope() as s:
        uid = s.execute(text("SELECT id FROM users WHERE tg_id=:tg"), {'tg': tg_id}).scalar()
        cid = s.execute(text("SELECT id FROM channels WHERE handle=:h"), {'h': handle}).scalar()
        if uid and cid:
            s.execute(text("DELETE FROM subscriptions WHERE user_id=:u AND channel_id=:c"), {'u': uid, 'c': cid})

def due_users(hour_now: int, minute_now: int):
    with session_scope() as s:
        res = s.execute(text("""
            SELECT * FROM users
            WHERE :h = ANY(digest_hours)
        """), {'h': hour_now}).mappings().all()
        return res

def add_messages(batch):
    if not batch:
        return
    from hashlib import sha256
    with session_scope() as s:
        for m in batch:
            h = sha256((m.get('text') or '').lower().encode('utf-8')).hexdigest()
            s.execute(text("""
                INSERT INTO messages(channel_id, tg_message_id, msg_date, link, text, text_hash)
                VALUES (:c, :mid, :dt, :link, :text, :h)
                ON CONFLICT (channel_id, tg_message_id) DO NOTHING
            """), {'c': m['channel_id'], 'mid': m['tg_message_id'], 'dt': m['msg_date'],
                     'link': m['link'], 'text': m['text'], 'h': h})

def get_user_window_messages(user_id: int, start_ts, end_ts):
    q = text("""
        SELECT m.* FROM messages m
        JOIN subscriptions s ON s.channel_id=m.channel_id
        WHERE s.user_id=:u AND m.msg_date BETWEEN :a AND :b
        ORDER BY m.msg_date DESC
        LIMIT 200
    """)
    with session_scope() as s:
        return s.execute(q, {'u': user_id, 'a': start_ts, 'b': end_ts}).mappings().all()

def save_digest(user_id: int, start_ts, end_ts, item_count: int, content_md: str, sent_to: str='user'):
    with session_scope() as s:
        s.execute(text("""
            INSERT INTO digests(user_id, window_start, window_end, item_count, content_md, sent_to)
            VALUES (:u,:a,:b,:n,:c,:to)
        """), {'u': user_id, 'a': start_ts, 'b': end_ts, 'n': item_count, 'c': content_md, 'to': sent_to})

def get_system_stats():
    """Получить статистику системы для отладки"""
    with session_scope() as s:
        stats = {}
        
        # Количество пользователей
        stats['users_count'] = s.execute(text("SELECT COUNT(*) FROM users")).scalar()
        
        # Количество активных каналов
        stats['active_channels'] = s.execute(text("SELECT COUNT(*) FROM channels WHERE status='active'")).scalar()
        
        # Количество подписок
        stats['subscriptions_count'] = s.execute(text("SELECT COUNT(*) FROM subscriptions")).scalar()
        
        # Количество сообщений за последние 24 часа
        stats['messages_24h'] = s.execute(text("""
            SELECT COUNT(*) FROM messages 
            WHERE msg_date > NOW() - INTERVAL '24 hours'
        """)).scalar()
        
        # Количество дайджестов за последние 24 часа
        stats['digests_24h'] = s.execute(text("""
            SELECT COUNT(*) FROM digests 
            WHERE created_at > NOW() - INTERVAL '24 hours'
        """)).scalar()
        
        return stats
