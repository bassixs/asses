from __future__ import annotations

import logging

from sqlalchemy import func, select

from bot.config import settings
from bot.database import async_session_maker
from bot.models import WebUser
from web.backend.auth import expected_password, hash_password, normalize_username

logger = logging.getLogger(__name__)


async def seed_bootstrap_admin() -> None:
    """Ensure at least one admin exists, so the site is never lockable-out.

    On a fresh install this turns the existing single WEB_LOGIN/WEB_PASSWORD credential
    into a real admin account, so the old sign-in keeps working while everyone else gets
    their own account through the users page. Idempotent: does nothing once any user exists.
    """
    password = expected_password()
    if not password:
        return  # auth disabled — nothing to bootstrap

    async with async_session_maker() as session:
        count = await session.scalar(select(func.count()).select_from(WebUser)) or 0
        if count > 0:
            return
        username = normalize_username(settings.web_login) or "admin"
        session.add(
            WebUser(
                username=username,
                password_hash=hash_password(password),
                is_admin=True,
                is_active=True,
            )
        )
        await session.commit()
        logger.info("Bootstrapped admin user '%s' from WEB_LOGIN/WEB_PASSWORD", username)
