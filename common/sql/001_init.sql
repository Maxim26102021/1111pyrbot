-- Create default postgres role (required for some tools)
DO $$   BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'postgres') THEN
        CREATE ROLE postgres WITH LOGIN SUPERUSER PASSWORD 'postgres_password';
    END IF;
END   $$;

-- Create prometeo role and database
CREATE ROLE prometeo WITH LOGIN PASSWORD 'promteo_password';
CREATE DATABASE prometeo OWNER prometeo;

-- Create tables
CREATE TABLE IF NOT EXISTS users (
                                     id SERIAL PRIMARY KEY,
                                     tg_id BIGINT UNIQUE NOT NULL,
                                     plan TEXT NOT NULL DEFAULT 'free',
                                     valid_until TIMESTAMPTZ,
                                     tz TEXT DEFAULT 'Europe/Amsterdam',
                                     digest_hours INTEGER[] DEFAULT ARRAY[9,19],
                                     created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

CREATE TABLE IF NOT EXISTS channels (
                                        id SERIAL PRIMARY KEY,
                                        handle TEXT UNIQUE NOT NULL,
                                        visibility TEXT NOT NULL DEFAULT 'public',
                                        status TEXT NOT NULL DEFAULT 'active',
                                        last_msg_id BIGINT DEFAULT 0,
                                        last_checked_at TIMESTAMPTZ,
                                        shard INTEGER DEFAULT 0,
                                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );

CREATE TABLE IF NOT EXISTS subscriptions (
                                             id SERIAL PRIMARY KEY,
                                             user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    channel_id INTEGER NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
    UNIQUE(user_id, channel_id)
    );

CREATE INDEX IF NOT EXISTS idx_subscriptions_user ON subscriptions(user_id);

CREATE TABLE IF NOT EXISTS messages (
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

CREATE INDEX IF NOT EXISTS idx_messages_channel_date ON messages(channel_id, msg_date DESC);

CREATE TABLE IF NOT EXISTS digests (
                                       id BIGSERIAL PRIMARY KEY,
                                       user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    window_start TIMESTAMPTZ NOT NULL,
    window_end TIMESTAMPTZ NOT NULL,
    item_count INTEGER NOT NULL,
    content_md TEXT NOT NULL,
    sent_to TEXT NOT NULL DEFAULT 'user',
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    );
