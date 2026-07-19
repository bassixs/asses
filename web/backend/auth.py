from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import secrets
import time
from pathlib import Path

from bot.config import settings

logger = logging.getLogger(__name__)

COOKIE_NAME = "hr40_session"
SESSION_TTL_SECONDS = 14 * 24 * 3600  # two weeks


def _secret_file() -> Path:
    return settings.download_dir.parent / "session_secret"


def _secret() -> bytes:
    """Key used to sign session cookies.

    Taken from SESSION_SECRET when set; otherwise generated once and persisted, so
    sessions survive restarts instead of logging everyone out on every deploy.
    """
    if settings.session_secret:
        return settings.session_secret.encode("utf-8")

    path = _secret_file()
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value.encode("utf-8")
        generated = secrets.token_urlsafe(48)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(generated, encoding="utf-8")
        path.chmod(0o600)
        return generated.encode("utf-8")
    except OSError:
        # Never take the site down over this: fall back to an in-process key. Sessions
        # then reset on restart, which is an inconvenience, not a security hole.
        logger.warning("Could not persist session secret at %s; using an ephemeral one", path)
        return _EPHEMERAL_SECRET


_EPHEMERAL_SECRET = secrets.token_urlsafe(48).encode("utf-8")


def expected_password() -> str:
    return settings.web_password or settings.admin_bot_password


def auth_required() -> bool:
    """Auth is disabled only when no password is configured at all."""
    return bool(expected_password())


def check_credentials(username: str, password: str) -> bool:
    """Compare both fields in constant time (login is case-insensitive)."""
    user_ok = hmac.compare_digest(
        (username or "").strip().casefold(), settings.web_login.casefold()
    )
    pass_ok = hmac.compare_digest(password or "", expected_password())
    return user_ok and pass_ok


def _sign(payload: str) -> str:
    digest = hmac.new(_secret(), payload.encode("utf-8"), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


def make_token(username: str) -> str:
    payload = f"{username}|{int(time.time()) + SESSION_TTL_SECONDS}"
    return f"{base64.urlsafe_b64encode(payload.encode('utf-8')).decode('ascii').rstrip('=')}.{_sign(payload)}"


def verify_token(token: str | None) -> str | None:
    """Return the signed-in username, or None if the token is missing/forged/expired."""
    if not token or "." not in token:
        return None
    encoded, _, signature = token.rpartition(".")
    try:
        padding = "=" * (-len(encoded) % 4)
        payload = base64.urlsafe_b64decode(encoded + padding).decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None

    if not hmac.compare_digest(_sign(payload), signature):
        return None

    username, _, expires = payload.rpartition("|")
    try:
        if int(expires) < time.time():
            return None
    except ValueError:
        return None
    return username or None
