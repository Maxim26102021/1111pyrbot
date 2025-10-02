import os
from contextlib import contextmanager
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

DB_URL = f"postgresql+psycopg2://{os.getenv('POSTGRES_USER')}:{os.getenv('POSTGRES_PASSWORD')}@{os.getenv('POSTGRES_HOST')}:{os.getenv('POSTGRES_PORT')}/{os.getenv('POSTGRES_DB')}"

engine = create_engine(DB_URL, pool_pre_ping=True, future=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, future=True)

def run_migrations():
    with engine.connect() as conn:
        # Проверка существующих таблиц
        tables = conn.execute(text("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")).fetchall()
        existing_tables = {row[0] for row in tables}

        # Определение необходимых таблиц
        required_tables = {'users', 'channels', 'subscriptions', 'messages', 'digests'}
        missing_tables = required_tables - existing_tables

        if missing_tables:
            # SQL для создания отсутствующих таблиц (без \c и дублирования ролей/базы)
            ddl = """
            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'users') THEN
                    CREATE TABLE users (
                        id SERIAL PRIMARY KEY,
                        tg_id BIGINT UNIQUE NOT NULL,
                        plan TEXT NOT NULL DEFAULT 'free',
                        valid_until TIMESTAMPTZ,
                        tz TEXT DEFAULT 'Europe/Amsterdam',
                        digest_hours INTEGER[] DEFAULT ARRAY[9,19],
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                END IF;
            END $$;

            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'channels') THEN
                    CREATE TABLE channels (
                        id SERIAL PRIMARY KEY,
                        handle TEXT UNIQUE NOT NULL,
                        visibility TEXT NOT NULL DEFAULT 'public',
                        status TEXT NOT NULL DEFAULT 'active',
                        last_msg_id BIGINT DEFAULT 0,
                        last_checked_at TIMESTAMPTZ,
                        shard INTEGER DEFAULT 0,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                END IF;
            END $$;

            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'subscriptions') THEN
                    CREATE TABLE subscriptions (
                        id SERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                        UNIQUE(user_id, channel_id)
                    );
                END IF;
            END $$;

            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'messages') THEN
                    CREATE TABLE messages (
                        id BIGSERIAL PRIMARY KEY,
                        channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
                        tg_message_id BIGINT NOT NULL,
                        msg_date TIMESTAMPTZ NOT NULL,
                        link TEXT,
                        text TEXT,
                        text_hash CHAR(64),
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        UNIQUE(channel_id, tg_message_id)
                    );
                END IF;
            END $$;

            DO $$ BEGIN
                IF NOT EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'digests') THEN
                    CREATE TABLE digests (
                        id BIGSERIAL PRIMARY KEY,
                        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                        window_start TIMESTAMPTZ NOT NULL,
                        window_end TIMESTAMPTZ NOT NULL,
                        item_count INTEGER NOT NULL,
                        content_md TEXT NOT NULL,
                        sent_to TEXT NOT NULL DEFAULT 'user',
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                    );
                END IF;
            END $$;

            -- Создание индексов, если таблица существует
            DO $$ BEGIN
                IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'subscriptions') THEN
                    CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);
                END IF;
            END $$;

            DO $$ BEGIN
                IF EXISTS (SELECT FROM pg_tables WHERE schemaname = 'public' AND tablename = 'messages') THEN
                    CREATE INDEX IF NOT EXISTS idx_messages_channel_date ON messages(channel_id, msg_date DESC);
                END IF;
            END $$;
            """
            conn.execute(text(ddl))
            conn.commit()
        else:
            print("All required tables already exist, skipping migrations.")

@contextmanager
def session_scope():
    session = SessionLocal()
    try:
        yield session
        session.commit()
    except:
        session.rollback()
        raise
    finally:
        session.close()
