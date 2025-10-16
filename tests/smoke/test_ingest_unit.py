from __future__ import annotations

import sys
import asyncio
from datetime import datetime, timezone
from types import ModuleType, SimpleNamespace


def _install_telethon_stub() -> None:
    telethon_module = ModuleType("telethon")
    events_module = ModuleType("telethon.events")
    errors_module = ModuleType("telethon.errors")

    class _NewMessage:  # minimal stub for type resolution
        Event = object

    events_module.NewMessage = _NewMessage

    class _TelegramClient:
        def __init__(self, *args, **kwargs) -> None:
            self.handlers = []

        def on(self, *args, **kwargs):  # pragma: no cover
            def decorator(func):
                self.handlers.append(func)
                return func

            return decorator

        async def start(self) -> None:  # pragma: no cover
            return None

        async def run_until_disconnected(self) -> None:  # pragma: no cover
            return None

        async def disconnect(self) -> None:  # pragma: no cover
            return None

        def is_connected(self) -> bool:  # pragma: no cover
            return False

    telethon_module.events = events_module
    telethon_module.errors = errors_module
    telethon_module.TelegramClient = _TelegramClient

    class _FloodWaitError(Exception):
        def __init__(self, seconds: int = 0) -> None:
            super().__init__(f"Flood wait {seconds}s")
            self.seconds = seconds

    errors_module.FloodWaitError = _FloodWaitError

    sys.modules.setdefault("telethon", telethon_module)
    sys.modules.setdefault("telethon.events", events_module)
    sys.modules.setdefault("telethon.errors", errors_module)


_install_telethon_stub()

from services.ingest.app.worker import MessageProcessor


class DummyQueue:
    def __init__(self) -> None:
        self.sent: list[int] = []

    def send_summarize_task(self, post_id: int) -> None:
        self.sent.append(post_id)


class DummySettings:
    database_url = "postgresql://localhost/dummy"


def make_event(message_id: int, text: str = "hello world", channel_id: int = 123) -> SimpleNamespace:
    peer = SimpleNamespace(channel_id=channel_id)
    message = SimpleNamespace(
        id=message_id,
        message=text,
        date=datetime.now(tz=timezone.utc),
        peer_id=peer,
    )
    chat = SimpleNamespace(title="Test Channel")
    return SimpleNamespace(message=message, chat=chat)


def test_message_processor_new_post(monkeypatch) -> None:
    queue = DummyQueue()
    processor = MessageProcessor(DummySettings(), queue)

    async def fake_get_or_create(database_url: str, tg_channel_id: int, title: str | None) -> int:
        return 10

    async def fake_upsert(database_url: str, **kwargs) -> tuple[int, bool]:
        return 77, True

    monkeypatch.setattr("services.ingest.app.worker.get_or_create_channel", fake_get_or_create)
    monkeypatch.setattr("services.ingest.app.worker.upsert_post", fake_upsert)

    asyncio.run(processor(make_event(1)))

    assert queue.sent == [77]


def test_message_processor_existing_post(monkeypatch) -> None:
    queue = DummyQueue()
    processor = MessageProcessor(DummySettings(), queue)

    async def fake_get_or_create(database_url: str, tg_channel_id: int, title: str | None) -> int:
        return 11

    async def fake_upsert(database_url: str, **kwargs) -> tuple[int, bool]:
        return 88, False

    monkeypatch.setattr("services.ingest.app.worker.get_or_create_channel", fake_get_or_create)
    monkeypatch.setattr("services.ingest.app.worker.upsert_post", fake_upsert)

    asyncio.run(processor(make_event(2)))

    assert queue.sent == []
