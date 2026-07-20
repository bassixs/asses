from __future__ import annotations

from collections.abc import AsyncGenerator

from fastapi import Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from bot.database import async_session_maker

# Legacy ownership sentinel for shared-workspace rows. Kept for rows that predate real
# users; new rows are stamped with the signed-in user's id for attribution.
WEB_OWNER_ID = 0


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session_maker() as session:
        yield session


class CurrentUser:
    """The signed-in user, populated by the auth middleware onto request.state."""

    def __init__(self, id: int, username: str, is_admin: bool) -> None:
        self.id = id
        self.username = username
        self.is_admin = is_admin


def current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "web_user", None)
    if user is None:
        # Auth disabled (no password configured): fall back to the legacy sentinel owner.
        return CurrentUser(id=WEB_OWNER_ID, username="—", is_admin=True)
    return user


def require_admin(user: CurrentUser = Depends(current_user)) -> CurrentUser:
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Только для администратора")
    return user
