# Promteo Digest Platform (refactor in progress)

## Быстрый старт (dev/mock)

1. Заполните `deploy/.env` и запустите профиль dev с моковым LLM:
   ```bash
   make dev-up
   ```

2. Примените миграции и подготовьте тестовые данные:
   ```bash
   make migrate
   make seed-demo
   ```

3. Отправьте демо-пост и дождитесь дайджеста:
   ```bash
   make fake-post
   # форсируем планировщик (однократно)
   python - <<'PY'
from services.scheduler.app.tasks import build_and_dispatch_digest
build_and_dispatch_digest()
PY
   ```

4. Посмотрите логи бота: `docker logs -f <контейнер bot>` — увидите JSON события `digest_delivered` и `messages_sent`.

## Prod профиль

1. Скопируйте пример переменных окружения и заполните значения:
   ```bash
   cp deploy/.env.sample deploy/.env
   ```

   Ключевая переменная для миграций: `DATABASE_URL=postgresql+asyncpg://digest:digest@postgres:5432/digest`

2. Поднимите базу данных и Redis:
   ```bash
   docker compose -f deploy/docker-compose.yml up -d postgres redis
   ```

3. Примените миграции (один раз) — можно локально или через compose:
   ```bash
   # установка зависимостей (однократно)
   pip install -r services/migrate/requirements.txt

   # локально
   DATABASE_URL=postgresql+asyncpg://digest:digest@localhost:5433/digest \
     python scripts/apply_migrations.py

   # либо внутри compose
   docker compose -f deploy/docker-compose.yml run --rm migrate
   ```

4. Продовый профиль стартует без моков:
   ```bash
   docker compose -f deploy/docker-compose.yml --profile prod up -d --build
   ```

## Telethon сессии

- Сервис `ingest` ожидает `.session` файлы в каталоге `./telethon_sessions` (он пробрасывается как volume в контейнер `/sessions`).
- Чтобы получить `.session`, используйте `telethon` скрипт авторизации (например, `reader/login_service_account.py`) и поместите готовый файл в `telethon_sessions/`.
- Если нужно задать конкретный набор каналов без БД, заполните `INGEST_CHANNEL_IDS` (CSV числовых `tg_channel_id`) и установите `INGEST_CHANNEL_SOURCE=env`.

## Summarizer

- Сервис `services/summarizer` поднимает FastAPI (`/health`, `/status`) и Celery worker для очередей `summarize`, `summarize_priority`.
- LLM вызывается через `libs/core/llm.py`; по умолчанию модель `LLM_MODEL=gpt-4o-mini`, таймаут `SUMMARIZE_TIMEOUT_SECONDS=45`. Кеширование идёт по `posts.text_hash`.
- При коротких текстах (< `MIN_TEXT_LEN`) сохраняется техническая заглушка, при RateLimit ловится `RateLimitError` и Celery делает экспоненциальные ретраи.
- Ручной запуск задачи из Python-консоли:
  ```python
  from services.summarizer.app.tasks import summarize_post
  summarize_post.delay(123)
  ```

## Scheduler

- `services/scheduler` — Celery Beat + worker, планирует задачу `build_and_dispatch_digest` с интервалом `DIGEST_PERIOD_MINUTES` и джиттером ±`DIGEST_JITTER_SECONDS`.
- Для каждого активного пользователя берёт summaries за `DIGEST_LOOKBACK_HOURS`, создаёт записи в `digests`/`digest_items` и ставит `send_digest` в очередь `QUEUE_BOT`.
- Проверить работу можно по логам Celery Beat (`docker compose logs scheduler`) — там будет видно следующее запускаемое время.

## Bot

- `services/bot` — тонкий aiogram 3.x бот: диалоги и доставка дайджестов.
- Celery worker слушает очередь `QUEUE_BOT` и отправляет сообщения chunk-и, учитывая `TELEGRAM_MAX_MESSAGE` и FLOOD_WAIT.
- Команда `/preview_sample` запрашивает свежие summary, при необходимости ставит задачи в `summarize_priority` и отправляет результат через `send_digest.delay`.
- В настройках можно задать `TELEGRAM_SLEEP_ON_FLOOD` (auto или секунды) и `PREVIEW_SAMPLE_LIMIT`.

## Payments

- `services/payments` — FastAPI вебхук, принимает события `payment.succeeded|failed|pending`, проверяет HMAC подпись и сохраняет платеж в `payments` с идемпотентным UPSERT.
- Успешные платежи активируют подписку пользователя: `DEFAULT_SUBSCRIPTION_PLAN` и продление на `SUBSCRIPTION_DURATION_DAYS`.
- Пример запроса:
  ```bash
  BODY='{"event":"payment.succeeded","ext_id":"abc123","user_id":1,"amount":299.00,"currency":"RUB","paid_at":"2025-10-16T18:00:00Z"}'
  SIG=$(python - <<'PY'
import hmac, binascii, hashlib, os
secret = os.environ.get('PAYMENTS_WEBHOOK_SECRET', 'secret')
body = os.environ['BODY'].encode()
print(hmac.new(secret.encode(), body, hashlib.sha256).hexdigest())
PY
)
  curl -X POST http://localhost:8080/webhook/tbank \
       -H "Content-Type: application/json" \
       -H "X-Signature: $SIG" \
       -d "$BODY"
  ```
  
## Структура

- `deploy/docker-compose.yml` — инфраструктура (Postgres, Redis, миграции, сервисы).
- `migrations/` — SQL миграции (выполняются по имени файла).
- `scripts/apply_migrations.py` — асинхронный раннер миграций.
- `libs/core/` — общие утилиты, DTO и клиенты.
- `services/*` — заготовки сервисов бот/ingest/summarizer/scheduler/payments.
- `tests/smoke/` — интеграционные проверки инфраструктуры.
- `tests/e2e/` — сценарий e2e-smoke без Telegram (использует mock LLM и in-memory DAO).
- `SECURITY.md` — чек-лист по безопасности и приватности.

## E2E smoke

Автотест `tests/e2e/test_smoke_flow.py` прогоняет цепочку «ингест → summarize → scheduler → bot» в памяти. Запустить вручную можно командой:
```bash
PYTHONPATH=. LLM_MODE=mock pytest tests/e2e/test_smoke_flow.py
```

## CI

GitHub Actions (`.github/workflows/ci.yml`) выполняет lint, pytest и сборку Docker-образов (`:ci-<sha>`). Артефакт `reports/junit.xml` доступен после прогона.

## Логи и метрики

- Все сервисы пишут JSON-логи через `libs.core.logging.json_log` (поля `event`, `service`, `latency_ms`, `user_id` и др.).
- Summarizer и payments имеют `/metrics` (JSON-счётчики запросов, ошибок, повторов).
- `docker logs -f <service>` — быстрый способ посмотреть поток событий; ищите `digest_enqueued`, `digest_delivered`, `webhook_processed`.

## Комплаенс и фич-флаги

- `COMPLIANCE_MODE=true` отключает потенциальные «чистки» и вспомогательные действия (флаг доступен в .env, кодом обрабатывается в сервисах).
- `LLM_MODE=mock` позволяет запускать платформу без подключения внешнего LLM (используется в dev профиле и тестах).
- Для деталей см. комментарии в `SECURITY.md` и код в `libs/core/llm.py`.

## Известные риски

- Передача текстов постов во внешний LLM может нарушать ToS каналов — используйте `LLM_MODE=mock`, если необходимо.
- Webhook-подписи необходимо хранить в секрете (`PAYMENTS_WEBHOOK_SECRET`). Ошибки подписи логируются.
- Телеграм-сессии должны храниться только локально (volume `telethon_sessions/`).

## Ссылки

- Product context: https://www.notion.so/Promteo-MVP-Telegram-2842f9d369f280438ac1c0ccb229116b?source=copy_link
