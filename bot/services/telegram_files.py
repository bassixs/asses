from __future__ import annotations

import asyncio
import logging
import re
from pathlib import Path

from aiogram import Bot
from aiogram.exceptions import TelegramBadRequest, TelegramNetworkError
from aiogram.types import File, Message

from bot.config import settings

logger = logging.getLogger(__name__)

SAFE_FILE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
SUPPORTED_AUDIO_DOCUMENT_EXTENSIONS = {".ogg", ".oga", ".opus", ".mp3", ".pcm", ".lpcm", ".raw"}


def extract_media_meta(message: Message) -> tuple[str, str | None, str, int | None, str | None]:
    if message.voice:
        return message.voice.file_id, message.voice.file_unique_id, "voice", message.voice.file_size, None
    if message.audio:
        return (
            message.audio.file_id,
            message.audio.file_unique_id,
            "audio",
            message.audio.file_size,
            message.audio.file_name,
        )
    if message.document:
        return (
            message.document.file_id,
            message.document.file_unique_id,
            "document",
            message.document.file_size,
            message.document.file_name,
        )
    raise ValueError("Unsupported message type")


def format_size(size_bytes: int) -> str:
    return f"{size_bytes / 1024 / 1024:.1f} МБ"


def is_telegram_file_too_big_error(exc: TelegramBadRequest) -> bool:
    return "file is too big" in str(exc).lower()


async def get_telegram_file_with_retry(bot: Bot, file_id: str) -> File:
    last_error: TelegramNetworkError | None = None
    for attempt in range(1, settings.telegram_file_download_attempts + 1):
        try:
            return await bot.get_file(file_id, request_timeout=settings.telegram_file_request_timeout_seconds)
        except TelegramNetworkError as exc:
            last_error = exc
            if attempt >= settings.telegram_file_download_attempts:
                break
            logger.warning(
                "Telegram get_file failed, retrying attempt=%s/%s: %s",
                attempt,
                settings.telegram_file_download_attempts,
                exc,
            )
            await asyncio.sleep(settings.telegram_file_download_retry_delay_seconds)
    assert last_error is not None
    raise last_error


async def download_telegram_path_with_retry(bot: Bot, file_path: str, destination: Path) -> None:
    last_error: TelegramNetworkError | None = None
    for attempt in range(1, settings.telegram_file_download_attempts + 1):
        try:
            await bot.download_file(
                file_path,
                destination=destination,
                timeout=settings.telegram_file_download_timeout_seconds,
            )
            return
        except TelegramNetworkError as exc:
            last_error = exc
            if attempt >= settings.telegram_file_download_attempts:
                break
            logger.warning(
                "Telegram download_file failed, retrying attempt=%s/%s: %s",
                attempt,
                settings.telegram_file_download_attempts,
                exc,
            )
            await asyncio.sleep(settings.telegram_file_download_retry_delay_seconds)
    assert last_error is not None
    raise last_error


async def download_telegram_file(bot: Bot, file_id: str, file_type: str, file_name: str | None = None) -> Path:
    tg_file = await get_telegram_file_with_retry(bot, file_id)
    if tg_file.file_path is None:
        raise RuntimeError("Telegram did not return file_path")
    suffix = Path(file_name or "").suffix or Path(tg_file.file_path or "").suffix or ".bin"
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    safe_file_id = SAFE_FILE_NAME_RE.sub("_", file_id)
    destination = settings.download_dir / f"{file_type}_{safe_file_id}{suffix}"
    await download_telegram_path_with_retry(bot, tg_file.file_path, destination)
    return destination
