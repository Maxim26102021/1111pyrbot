from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Iterable, Sequence

from telethon import TelegramClient, events
from telethon.errors import FloodWaitError

from libs.core.util import next_backoff

logger = logging.getLogger(__name__)

MessageHandler = Callable[[events.NewMessage.Event], Awaitable[None]]


class TelethonShard:
    def __init__(
        self,
        *,
        session_path: Path,
        api_id: int,
        api_hash: str,
        channels: Sequence[int],
        handler: MessageHandler,
    ) -> None:
        self.session_path = session_path
        self.api_id = api_id
        self.api_hash = api_hash
        self.channels = list(channels)
        self.handler = handler
        self._client: TelegramClient | None = None

    def build_client(self) -> TelegramClient:
        client = TelegramClient(
            session=str(self.session_path),
            api_id=self.api_id,
            api_hash=self.api_hash,
            auto_reconnect=True,
            connection_retries=999,
            retry_delay=5,
            flood_sleep_threshold=60,
        )

        @client.on(events.NewMessage(chats=self.channels))
        async def _on_new_message(event: events.NewMessage.Event) -> None:
            await self.handler(event)

        return client

    async def run(self) -> None:
        client = self.build_client()
        self._client = client
        attempt = 0
        while True:
            try:
                logger.info(
                    "Starting shard",
                    extra={
                        "session": str(self.session_path),
                        "channels": self.channels,
                    },
                )
                await client.start()
                await client.run_until_disconnected()
            except FloodWaitError as exc:
                delay = exc.seconds + 5
                logger.warning(
                    "Flood wait detected, sleeping",
                    extra={
                        "session": str(self.session_path),
                        "sleep_seconds": delay,
                        "flood_wait_seconds": exc.seconds,
                    },
                )
                await asyncio.sleep(delay)
            except Exception as exc:
                attempt += 1
                delay = next_backoff(attempt, base=5, maximum=300)
                logger.exception(
                    "Shard crashed, retrying",
                    extra={
                        "session": str(self.session_path),
                        "attempt": attempt,
                        "sleep_seconds": delay,
                    },
                )
                await asyncio.sleep(delay)
            else:
                attempt = 0

    async def disconnect(self) -> None:
        if self._client and self._client.is_connected():
            await self._client.disconnect()
