from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import WebUser
from web.backend.auth import generate_password, hash_password, normalize_username
from web.backend.deps import CurrentUser, current_user, get_session, require_admin

logger = logging.getLogger(__name__)
router = APIRouter(tags=["users"])


class UserCreate(BaseModel):
    username: str
    is_admin: bool = False


class UserPatch(BaseModel):
    is_active: bool | None = None
    is_admin: bool | None = None


def _out(user: WebUser, *, me_id: int) -> dict:
    return {
        "id": user.id,
        "username": user.username,
        "is_admin": user.is_admin,
        "is_active": user.is_active,
        "created_at": user.created_at,
        "last_login": user.last_login,
        "is_self": user.id == me_id,
    }


async def _active_admin_count(session: AsyncSession, *, exclude: int | None = None) -> int:
    stmt = select(func.count()).select_from(WebUser).where(
        WebUser.is_admin.is_(True), WebUser.is_active.is_(True)
    )
    if exclude is not None:
        stmt = stmt.where(WebUser.id != exclude)
    return await session.scalar(stmt) or 0


@router.get("/users")
async def list_users(
    me: CurrentUser = Depends(require_admin), session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = await session.scalars(select(WebUser).order_by(WebUser.id))
    return [_out(u, me_id=me.id) for u in rows]


@router.post("/users")
async def create_user(
    payload: UserCreate,
    me: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    username = normalize_username(payload.username)
    if not username:
        raise HTTPException(status_code=400, detail="Укажите логин.")
    if len(username) < 3:
        raise HTTPException(status_code=400, detail="Логин слишком короткий (минимум 3 символа).")
    exists = await session.scalar(select(WebUser.id).where(WebUser.username == username))
    if exists is not None:
        raise HTTPException(status_code=400, detail="Такой логин уже занят.")

    password = generate_password()
    user = WebUser(
        username=username,
        password_hash=hash_password(password),
        is_admin=payload.is_admin,
        is_active=True,
    )
    session.add(user)
    await session.commit()
    await session.refresh(user)
    logger.info("User '%s' created '%s' (admin=%s)", me.username, username, payload.is_admin)
    # Plaintext returned exactly once — it is never stored anywhere.
    return {**_out(user, me_id=me.id), "password": password}


@router.post("/users/{user_id}/reset-password")
async def reset_password(
    user_id: int,
    me: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await session.get(WebUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    password = generate_password()
    user.password_hash = hash_password(password)
    await session.commit()
    logger.info("User '%s' reset password for '%s'", me.username, user.username)
    return {**_out(user, me_id=me.id), "password": password}


@router.patch("/users/{user_id}")
async def patch_user(
    user_id: int,
    payload: UserPatch,
    me: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await session.get(WebUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")

    if payload.is_active is not None and payload.is_active != user.is_active:
        if not payload.is_active and user.is_admin and await _active_admin_count(session, exclude=user.id) == 0:
            raise HTTPException(status_code=400, detail="Нельзя отключить последнего администратора.")
        user.is_active = payload.is_active

    if payload.is_admin is not None and payload.is_admin != user.is_admin:
        if not payload.is_admin and await _active_admin_count(session, exclude=user.id) == 0:
            raise HTTPException(status_code=400, detail="Нельзя снять роль с последнего администратора.")
        user.is_admin = payload.is_admin

    await session.commit()
    return _out(user, me_id=me.id)


@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    me: CurrentUser = Depends(require_admin),
    session: AsyncSession = Depends(get_session),
) -> dict:
    user = await session.get(WebUser, user_id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    if user.id == me.id:
        raise HTTPException(status_code=400, detail="Нельзя удалить свой собственный аккаунт.")
    if user.is_admin and await _active_admin_count(session, exclude=user.id) == 0:
        raise HTTPException(status_code=400, detail="Нельзя удалить последнего администратора.")
    await session.delete(user)
    await session.commit()
    logger.info("User '%s' deleted '%s'", me.username, user.username)
    return {"ok": True}


@router.post("/users/me/password")
async def change_own_password(
    me: CurrentUser = Depends(current_user), session: AsyncSession = Depends(get_session)
) -> dict:
    """Rotate one's own password to a fresh strong one (shown once)."""
    user = await session.get(WebUser, me.id)
    if user is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    password = generate_password()
    user.password_hash = hash_password(password)
    await session.commit()
    return {"ok": True, "password": password}
