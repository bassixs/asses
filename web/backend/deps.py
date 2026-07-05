from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import async_session_maker

# Telegram-specific ownership columns (chat_id/user_id) are non-null on the shared models.
# Until the web app has real auth/users, web-created rows use this sentinel owner.
WEB_OWNER_ID = 0


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session
