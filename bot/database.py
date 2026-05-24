from __future__ import annotations

from pathlib import Path

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


async def init_db() -> None:
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.rsplit("///", maxsplit=1)[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
