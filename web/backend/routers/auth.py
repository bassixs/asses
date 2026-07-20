from __future__ import annotations

import logging
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import WebUser
from web.backend.auth import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    auth_required,
    make_token,
    normalize_username,
    verify_password,
    verify_token,
)
from web.backend.deps import get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(
    payload: LoginPayload,
    request: Request,
    response: Response,
    session: AsyncSession = Depends(get_session),
) -> dict:
    username = normalize_username(payload.username)
    user = await session.scalar(select(WebUser).where(WebUser.username == username))
    # Verify a hash even when the user is missing, so timing doesn't reveal valid logins.
    stored = user.password_hash if user else "pbkdf2_sha256$1$00$00"
    ok = verify_password(payload.password, stored) and user is not None and user.is_active

    if not ok:
        client = request.client.host if request.client else "?"
        logger.warning("Failed sign-in for '%s' from %s", username[:40], client)
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    user.last_login = datetime.now(timezone.utc)
    await session.commit()

    response.set_cookie(
        COOKIE_NAME,
        make_token(user.username),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        samesite="lax",
        secure=request.url.scheme == "https",
        path="/",
    )
    return {"ok": True, "username": user.username, "is_admin": user.is_admin}


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    if not auth_required():
        return {"authenticated": True, "username": "—", "is_admin": True, "auth_disabled": True}
    username = verify_token(request.cookies.get(COOKIE_NAME))
    user = (
        await session.scalar(select(WebUser).where(WebUser.username == username))
        if username
        else None
    )
    if user is None or not user.is_active:
        raise HTTPException(status_code=401, detail="Не выполнен вход")
    return {"authenticated": True, "username": user.username, "is_admin": user.is_admin}
