from __future__ import annotations

import asyncio
import logging

from aiogram import Dispatcher

from .handlers import register_handlers
from .messaging import bot, settings

dp = Dispatcher()
register_handlers(dp, settings)


async def _run_polling() -> None:
    await dp.start_polling(bot)


def main() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    asyncio.run(_run_polling())


if __name__ == "__main__":
    main()
