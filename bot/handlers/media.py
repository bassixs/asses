from __future__ import annotations

from html import escape
import logging
import re
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.types import Message
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import transcript_actions_keyboard
from bot.models import InterviewRecord
from bot.services.speechkit import SpeechKitError, transcribe_file

logger = logging.getLogger(__name__)
router = Router()

_SAFE_FILE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")
SUPPORTED_AUDIO_DOCUMENT_EXTENSIONS = {".ogg", ".oga", ".opus", ".mp3", ".pcm", ".lpcm", ".raw"}


def _extract_file_meta(message: Message) -> tuple[str, str | None, str, int | None, str | None]:
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


def _format_size(size_bytes: int) -> str:
    return f"{size_bytes / 1024 / 1024:.1f} МБ"


def _is_telegram_file_too_big_error(exc: TelegramBadRequest) -> bool:
    return "file is too big" in str(exc).lower()


async def _download_telegram_file(bot: Bot, file_id: str, file_type: str, file_name: str | None = None) -> Path:
    tg_file = await bot.get_file(file_id, request_timeout=settings.telegram_file_request_timeout_seconds)
    if tg_file.file_path is None:
        raise RuntimeError("Telegram did not return file_path")
    suffix = Path(file_name or "").suffix or Path(tg_file.file_path or "").suffix or ".bin"
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    safe_file_id = _SAFE_FILE_NAME_RE.sub("_", file_id)
    destination = settings.download_dir / f"{file_type}_{safe_file_id}{suffix}"
    await bot.download_file(
        tg_file.file_path,
        destination=destination,
        timeout=settings.telegram_file_download_timeout_seconds,
    )
    return destination


@router.message(F.voice | F.audio | F.document)
async def handle_interview_file(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя. Попробуйте ещё раз.")
        return

    file_id, file_unique_id, file_type, file_size, file_name = _extract_file_meta(message)
    if message.document:
        suffix = Path(file_name or "").suffix.lower()
        if suffix not in SUPPORTED_AUDIO_DOCUMENT_EXTENSIONS:
            await message.answer(
                "Этот документ не похож на поддерживаемую аудиозапись. "
                "Для блокнота наблюдателя отправьте .xlsx, для аудио — .ogg/.opus/.mp3/.pcm."
            )
            return

    if file_size is not None and file_size > settings.telegram_download_max_bytes:
        await message.answer(
            "Файл слишком большой для прямого скачивания через Telegram Bot API.\n\n"
            f"Размер файла: {_format_size(file_size)}\n"
            f"Текущий лимит: {_format_size(settings.telegram_download_max_bytes)}\n\n"
            "Сейчас можно отправить файл меньше лимита или разделить запись на части. "
            "Для больших записей следующим шагом лучше добавить загрузку по ссылке из облака/диска."
        )
        return

    await message.answer("Файл получен. Скачиваю и отправляю на расшифровку...")
    logger.info("Received %s from user_id=%s chat_id=%s", file_type, message.from_user.id, message.chat.id)

    try:
        local_path = await _download_telegram_file(bot, file_id, file_type, file_name)
        transcript = await transcribe_file(local_path)
    except SpeechKitError as exc:
        logger.exception("SpeechKit failed")
        await message.answer(f"Не удалось расшифровать запись: {escape(str(exc), quote=False)}")
        return
    except TelegramBadRequest as exc:
        logger.exception("Telegram failed to provide media file")
        if _is_telegram_file_too_big_error(exc):
            await message.answer(
                "Файл слишком большой для прямого скачивания через Telegram Bot API. "
                f"Попробуйте отправить запись до {_format_size(settings.telegram_download_max_bytes)} "
                "или разбить интервью на несколько файлов."
            )
        else:
            await message.answer(f"Telegram не отдал файл для обработки: {escape(str(exc), quote=False)}")
        return
    except Exception:
        logger.exception("Unexpected media handling error")
        await message.answer("Произошла ошибка при обработке файла. Попробуйте позже.")
        return

    record = InterviewRecord(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_type=file_type,
        file_path=str(local_path),
        transcript=transcript,
    )
    session.add(record)
    await session.commit()
    await session.refresh(record)

    await message.answer(
        f"✅ Расшифровано. ID: {record.id}. Напиши /assess {record.id} для оценки по компетенциям",
        reply_markup=transcript_actions_keyboard(record.id),
    )
