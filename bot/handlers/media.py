from __future__ import annotations

from html import escape
import logging
from pathlib import Path

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, FSInputFile, Message
from sqlalchemy import desc, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import InterviewRecord, MediaProcessingJob
from bot.services.speechkit import normalize_transcript_text
from bot.services.telegram_files import (
    SUPPORTED_AUDIO_DOCUMENT_EXTENSIONS,
    extract_media_meta,
    format_size,
)
from bot.services.transcript_export import build_transcript_text_file

logger = logging.getLogger(__name__)
router = Router()


@router.message(F.voice | F.audio | F.document)
async def handle_interview_file(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя. Попробуйте ещё раз.")
        return

    try:
        file_id, file_unique_id, file_type, file_size, file_name = extract_media_meta(message)
    except ValueError:
        await message.answer("Этот тип сообщения не поддерживается.")
        return

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
            "Файл слишком большой для текущей настройки скачивания.\n\n"
            f"Размер файла: {format_size(file_size)}\n"
            f"Текущий лимит: {format_size(settings.telegram_download_max_bytes)}"
        )
        return

    job = MediaProcessingJob(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_type=file_type,
        file_name=file_name,
        file_size=file_size,
        status="queued",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    logger.info("Queued media job id=%s file_type=%s user_id=%s chat_id=%s", job.id, file_type, job.user_id, job.chat_id)
    await message.answer(
        f"Задача #{job.id}: файл получен и поставлен в очередь.\n"
        "Я пришлю статусы обработки и сообщение с кнопкой скачивания после расшифровки."
    )


@router.callback_query(F.data.startswith("transcript_file:"))
async def callback_transcript_file(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось обработать запрос", show_alert=True)
        return

    record_id = int(callback.data.split(":", maxsplit=1)[1])
    record = await session.scalar(
        select(InterviewRecord).where(
            InterviewRecord.id == record_id,
            InterviewRecord.user_id == callback.from_user.id,
        )
    )
    if record is None:
        await callback.answer("Запись не найдена", show_alert=True)
        return
    if not record.transcript_file_path:
        await callback.answer("Файл расшифровки пока не сформирован", show_alert=True)
        return

    path = Path(record.transcript_file_path)
    if not path.exists():
        await callback.answer("Файл расшифровки не найден на сервере", show_alert=True)
        return

    await callback.answer("Отправляю файл")
    await callback.message.answer_document(
        FSInputFile(path, filename=path.name),
        caption=f"Расшифровка записи #{record.id}",
    )


@router.message(Command("my_records"))
async def cmd_my_records(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    records = list(
        await session.scalars(
            select(InterviewRecord)
            .where(InterviewRecord.user_id == message.from_user.id)
            .order_by(desc(InterviewRecord.created_at))
            .limit(10)
        )
    )
    if not records:
        await message.answer("У вас пока нет расшифрованных записей.")
        return

    lines = ["Последние расшифрованные записи:"]
    for record in records:
        lines.append(f"#{record.id}: {record.file_type}, {len(record.transcript)} символов")
    await message.answer(escape("\n".join(lines), quote=False))


@router.message(Command("rebuild_transcript"))
async def cmd_rebuild_transcript(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    args = (message.text or "").split(maxsplit=1)
    if len(args) != 2 or not args[1].strip().isdigit():
        await message.answer("Формат: /rebuild_transcript <ID записи>\nНапример: /rebuild_transcript 1")
        return

    record_id = int(args[1].strip())
    record = await session.scalar(
        select(InterviewRecord).where(
            InterviewRecord.id == record_id,
            InterviewRecord.user_id == message.from_user.id,
        )
    )
    if record is None:
        await message.answer("Запись не найдена.")
        return

    await message.answer("Пересобираю файл расшифровки: очищаю повторы и заново размечаю роли...")
    record.transcript = normalize_transcript_text(record.transcript)
    await session.commit()

    transcript_path = await build_transcript_text_file(transcript=record.transcript, record_id=record.id)
    record.transcript_file_path = str(transcript_path)
    await session.commit()

    await message.answer_document(
        FSInputFile(transcript_path, filename=transcript_path.name),
        caption=f"Обновлённая расшифровка записи #{record.id}",
    )
