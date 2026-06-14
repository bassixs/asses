from __future__ import annotations

import asyncio
import logging
import sys
from collections.abc import Awaitable, Callable
from typing import Any

from aiogram import BaseMiddleware, Bot, Dispatcher
from aiogram.client.session.aiohttp import AiohttpSession
from aiogram.client.telegram import TelegramAPIServer
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import TelegramObject

from bot.config import settings
from bot.database import async_session_maker, init_db
from bot.handlers import admin, assessment, common, guided, media, notebook, workflow
from bot.services.media_jobs import start_media_job_worker


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

    session: AiohttpSession | None = None
    if settings.telegram_api_base_url:
        api_server = TelegramAPIServer.from_base(
            settings.telegram_api_base_url,
            is_local=settings.telegram_api_is_local,
        )
        session = AiohttpSession(api=api_server)

    bot = Bot(token=settings.bot_token, session=session)
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.update.middleware(DbSessionMiddleware())
    dispatcher.include_router(admin.router)
    dispatcher.include_router(common.router)
    dispatcher.include_router(guided.router)
    dispatcher.include_router(workflow.router)
    dispatcher.include_router(assessment.router)
    dispatcher.include_router(notebook.router)
    dispatcher.include_router(media.router)

    await bot.delete_webhook(drop_pending_updates=settings.telegram_drop_pending_updates_on_start)
    logging.getLogger(__name__).info("Bot started")
    media_worker = start_media_job_worker(bot)
    try:
        await dispatcher.start_polling(bot, allowed_updates=dispatcher.resolve_used_update_types())
    finally:
        media_worker.cancel()
        try:
            await media_worker
        except asyncio.CancelledError:
            pass
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
