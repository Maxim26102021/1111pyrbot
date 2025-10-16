# Promteo Digest Platform (refactor in progress)

## Быстрый старт окружения

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

4. После первого запуска `docker compose -f deploy/docker-compose.yml up -d` автоматически выполнит сервис `migrate` и лишь затем стартует остальные приложения.

## Telethon сессии

- Сервис `ingest` ожидает `.session` файлы в каталоге `./telethon_sessions` (он пробрасывается как volume в контейнер `/sessions`).
- Чтобы получить `.session`, используйте `telethon` скрипт авторизации (например, `reader/login_service_account.py`) и поместите готовый файл в `telethon_sessions/`.
- Если нужно задать конкретный набор каналов без БД, заполните `INGEST_CHANNEL_IDS` (CSV числовых `tg_channel_id`) и установите `INGEST_CHANNEL_SOURCE=env`.

## Структура

- `deploy/docker-compose.yml` — инфраструктура (Postgres, Redis, миграции, сервисы).
- `migrations/` — SQL миграции (выполняются по имени файла).
- `scripts/apply_migrations.py` — асинхронный раннер миграций.
- `libs/core/` — общие утилиты, DTO и клиенты.
- `services/*` — заготовки сервисов бот/ingest/summarizer/scheduler/payments.
- `tests/smoke/` — интеграционные проверки инфраструктуры.

## Ссылки

- Product context: https://www.notion.so/Promteo-MVP-Telegram-2842f9d369f280438ac1c0ccb229116b?source=copy_link
