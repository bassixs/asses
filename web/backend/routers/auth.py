from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from web.backend.auth import (
    COOKIE_NAME,
    SESSION_TTL_SECONDS,
    auth_required,
    check_credentials,
    make_token,
    verify_token,
)

logger = logging.getLogger(__name__)
router = APIRouter(tags=["auth"])


class LoginPayload(BaseModel):
    username: str
    password: str


@router.post("/auth/login")
async def login(payload: LoginPayload, request: Request, response: Response) -> dict:
    if not check_credentials(payload.username, payload.password):
        client = request.client.host if request.client else "?"
        logger.warning("Failed sign-in attempt for '%s' from %s", payload.username[:40], client)
        # Deliberately vague: do not reveal which of the two fields was wrong.
        raise HTTPException(status_code=401, detail="Неверный логин или пароль")

    response.set_cookie(
        COOKIE_NAME,
        make_token(payload.username.strip()),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,       # not readable from JavaScript
        samesite="lax",      # not sent on cross-site requests
        secure=request.url.scheme == "https",
        path="/",
    )
    return {"ok": True, "username": payload.username.strip()}


@router.post("/auth/logout")
async def logout(response: Response) -> dict:
    response.delete_cookie(COOKIE_NAME, path="/")
    return {"ok": True}


@router.get("/auth/me")
async def me(request: Request) -> dict:
    if not auth_required():
        return {"authenticated": True, "username": "—", "auth_disabled": True}
    username = verify_token(request.cookies.get(COOKIE_NAME))
    if not username:
        raise HTTPException(status_code=401, detail="Не выполнен вход")
    return {"authenticated": True, "username": username}
