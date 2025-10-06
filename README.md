Понял. Вот готовый README.md файл для твоего GitHub-репозитория. Он структурирован, содержит всю необходимую информацию для быстрого старта и понимания проекта.

Просто скопируй весь текст ниже и вставь его в файл README.md в корне твоего проекта.

Promteo MVP: Персональный новостной агрегатор для Telegram

Promteo MVP — это Telegram-бот, который выступает в роли персонального новостного агрегатора. Пользователи могут подписываться на интересующие их публичные Telegram-каналы, а бот будет периодически собирать из них новые посты, генерировать краткую сводку (дайджест) с помощью LLM (Google Gemini) и присылать пользователю в личные сообщения.

✨ Основные возможности

Подписка на каналы: Добавляйте, удаляйте и просматривайте список ваших источников.

Гибкое расписание: Настраивайте часы, в которые вы хотите получать дайджесты.

AI-саммаризация: Дайджесты генерируются с помощью Google Gemini для краткости и ясности.

Ручной запрос: Получите дайджест за последнее временное окно в любой момент по команде.

🚀 Технологический стек

Язык: Python 3.11

Telegram-интеграция: Pyrogram

База данных: PostgreSQL 16

Взаимодействие с БД: SQLAlchemy Core

Планировщик задач: APScheduler

Генерация текста: Google Generative AI (Gemini 1.5 Flash)

Оркестрация: Docker, Docker Compose

🏗️ Архитектура

Проект построен на микросервисной архитектуре и состоит из следующих компонентов:

bot: Основной сервис-бот, который общается с пользователями через Telegram Bot API. Принимает команды, отправляет дайджесты.

reader: Фоновый сервис-парсер. Работает как пользовательский аккаунт Telegram (через MTProto), сканирует каналы-источники и сохраняет новые посты в базу данных.

db: Сервис базы данных PostgreSQL, служащий единым хранилищем для всех данных.

redis: Сервис для кэширования (зарезервирован для будущего использования).

⚙️ Установка и запуск
1. Предварительные требования

Docker и Docker Compose установлены на вашем сервере.

Telegram API credentials:

API_ID и API_HASH с my.telegram.org.

BOT_TOKEN, полученный от @BotFather.

Google Gemini API Key:

GEMINI_API_KEY, полученный из Google AI Studio.

2. Конфигурация

Клонируйте репозиторий:

code
Bash
download
content_copy
expand_less
git clone <your-repo-url>
cd promteo_mvp

Создайте файл .env в корне проекта, скопировав env.example (если он есть) или создав новый:

code
Bash
download
content_copy
expand_less
cp env.example .env

Заполните файл .env вашими реальными данными:

code
Dotenv
download
content_copy
expand_less
# ==== TELEGRAM BOT ====
BOT_TOKEN=123456:ABC-DEF123456...

# ==== TELEGRAM MTProto service account (Reader & Bot) ====
TELEGRAM_API_ID=12345678
TELEGRAM_API_HASH=abcdef1234567890abcdef123456...

# ==== DATABASE ====
POSTGRES_HOST=db
POSTGRES_PORT=5432
POSTGRES_DB=promteo
POSTGRES_USER=promteo
POSTGRES_PASSWORD=supersecretpassword

# ==== APP ====
TZ=Europe/Moscow

# ==== LLM (Gemini) ====
GEMINI_API_KEY=AIzaSy...
3. Первый запуск reader-а для авторизации

Сервису reader необходимо один раз авторизоваться как пользовательский аккаунт.

Запустите только сервис reader:

code
Bash
download
content_copy
expand_less
docker compose up reader

Pyrogram попросит вас ввести номер телефона, код из Telegram и, возможно, пароль двухфакторной аутентификации.

После успешной авторизации в папке sessions/ будет создан файл service1.session (или с именем, указанным в TELEGRAM_SESSION_NAME).

Остановите процесс (Ctrl+C).

4. Запуск всего проекта

Теперь можно запустить все сервисы в фоновом режиме.

code
Bash
download
content_copy
expand_less
docker compose up -d --build

Эта команда соберет образы (если они изменились) и запустит все контейнеры.

5. Проверка статуса
code
Bash
download
content_copy
expand_less
docker compose ps

Все сервисы должны иметь статус Up (healthy) или running.

🤖 Команды бота

/start — Начать работу и получить список команд.

/add @channel_name — Добавить канал в список источников.

/list — Показать список ваших источников.

/remove @channel_name — Удалить канал из списка.

/when HH:MM HH:MM — Установить часы для получения дайджестов (например, /when 09:00 21:00).

/digest_now — Немедленно сгенерировать и прислать дайджест за последнее временное окно.

🗃️ Доступ к базе данных

Для удобной работы с базой данных (например, через DBeaver) можно пробросить порт PostgreSQL на локальную машину.

Создайте файл docker-compose.override.yml в корне проекта:

code
Yaml
download
content_copy
expand_less
services:
  db:
    ports:
      - "5433:5432" # Проброс порта 5432 контейнера на порт 5433 хоста

Перезапустите сервисы:

code
Bash
download
content_copy
expand_less
docker compose up -d

Теперь вы можете подключиться к базе данных, используя следующие параметры:

Host: localhost (или IP вашего сервера)

Port: 5433

Database: promteo

User: promteo

Password: пароль из вашего .env файла

Если ваш сервер находится за файрволом, используйте SSH-туннель в настройках вашего SQL-клиента.
