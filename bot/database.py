from __future__ import annotations

from pathlib import Path

from sqlalchemy import event
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from bot.config import settings

engine = create_async_engine(settings.database_url, echo=False, pool_pre_ping=True)
async_session_maker = async_sessionmaker(engine, expire_on_commit=False, class_=AsyncSession)


if settings.database_url.startswith("sqlite"):

    @event.listens_for(engine.sync_engine, "connect")
    def _sqlite_pragmas(dbapi_connection, _record) -> None:
        """Tune SQLite for concurrent access.

        WAL lets readers and writers run without blocking each other (default rollback
        journaling locks the whole file during a write). busy_timeout makes a query that
        hits a lock wait rather than fail; NORMAL sync is durable enough under WAL and
        much faster on commits.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=5000")
        cursor.execute("PRAGMA synchronous=NORMAL")
        cursor.close()


async def init_db() -> None:
    if settings.database_url.startswith("sqlite"):
        db_path = settings.database_url.rsplit("///", maxsplit=1)[-1]
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
