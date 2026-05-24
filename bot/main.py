from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.types import TelegramObject

from bot.config import settings
from bot.database import async_session_maker, init_db
from bot.handlers import assessment, common, media
from bot.keyboards import main_menu_keyboard


class DbSessionMiddleware(BaseMiddleware):
    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        async with async_session_maker() as session:
            data["session"] = session
            return await handler(event, data)


def setup_logging() -> None:
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
        stream=sys.stdout,
    )


async def main() -> None:
    setup_logging()
    await init_db()

    bot = Bot(token=settings.bot_token)
    dispatcher = Dispatcher()
    dispatcher.update.middleware(DbSessionMiddleware())
    dispatcher.include_router(common.router)
    dispatcher.include_router(assessment.router)
    dispatcher.include_router(media.router)

    await bot.delete_webhook(drop_pending_updates=True)
    logging.getLogger(__name__).info("Bot started")
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
