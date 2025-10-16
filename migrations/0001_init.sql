-- PostgreSQL 16 initialization script

CREATE TABLE IF NOT EXISTS users (
  id           BIGSERIAL PRIMARY KEY,
  tg_user_id   BIGINT UNIQUE NOT NULL,
  lang         TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS subscriptions (
  id           BIGSERIAL PRIMARY KEY,
  user_id      BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  status       TEXT NOT NULL,
  plan         TEXT,
  trial_until  TIMESTAMPTZ,
  paid_until   TIMESTAMPTZ,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS channels (
  id            BIGSERIAL PRIMARY KEY,
  tg_channel_id BIGINT UNIQUE NOT NULL,
  title         TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS user_channels (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  channel_id  BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  added_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, channel_id)
);

CREATE TABLE IF NOT EXISTS posts (
  id            BIGSERIAL PRIMARY KEY,
  channel_id    BIGINT NOT NULL REFERENCES channels(id) ON DELETE CASCADE,
  message_id    BIGINT NOT NULL,
  published_at  TIMESTAMPTZ,
  text_hash     TEXT,
  raw_text      TEXT,
  created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (channel_id, message_id)
);

CREATE INDEX IF NOT EXISTS idx_posts_channel_created
  ON posts (channel_id, created_at DESC);

CREATE TABLE IF NOT EXISTS summaries (
  id           BIGSERIAL PRIMARY KEY,
  post_id      BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  summary_text TEXT NOT NULL,
  model        TEXT,
  tokens_in    INT,
  tokens_out   INT,
  cost         DOUBLE PRECISION,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (post_id)
);

CREATE TABLE IF NOT EXISTS digests (
  id          BIGSERIAL PRIMARY KEY,
  user_id     BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  slot        TEXT,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS digest_items (
  id          BIGSERIAL PRIMARY KEY,
  digest_id   BIGINT NOT NULL REFERENCES digests(id) ON DELETE CASCADE,
  post_id     BIGINT NOT NULL REFERENCES posts(id) ON DELETE CASCADE,
  order_index INT NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_digest_items_digest
  ON digest_items (digest_id, order_index);

CREATE TABLE IF NOT EXISTS payments (
  id         BIGSERIAL PRIMARY KEY,
  user_id    BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  provider   TEXT NOT NULL,
  ext_id     TEXT,
  amount     NUMERIC(12,2),
  currency   TEXT DEFAULT 'RUB',
  status     TEXT,
  payload    JSONB,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE OR REPLACE FUNCTION touch_subscriptions_updated_at()
RETURNS TRIGGER AS $$
BEGIN
  NEW.updated_at = now();
  RETURN NEW;
END; $$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_subscriptions_touch ON subscriptions;
CREATE TRIGGER trg_subscriptions_touch
BEFORE UPDATE ON subscriptions
FOR EACH ROW
EXECUTE FUNCTION touch_subscriptions_updated_at();

CREATE INDEX IF NOT EXISTS idx_user_channels_user ON user_channels(user_id);
CREATE INDEX IF NOT EXISTS idx_user_channels_channel ON user_channels(channel_id);
CREATE INDEX IF NOT EXISTS idx_summaries_created ON summaries(created_at DESC);
CREATE INDEX IF NOT EXISTS idx_payments_user_created ON payments(user_id, created_at DESC);
