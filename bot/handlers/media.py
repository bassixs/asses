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
from bot.keyboards import stt_provider_keyboard
from bot.models import Exercise, InterviewRecord, MediaProcessingJob, Participant
from bot.services.role_labeling import RoleLabelingError, label_transcript_roles
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
        status="awaiting_provider",
    )
    session.add(job)
    await session.commit()
    await session.refresh(job)

    logger.info(
        "Media job id=%s is waiting for STT provider file_type=%s user_id=%s chat_id=%s",
        job.id,
        file_type,
        job.user_id,
        job.chat_id,
    )
    await message.answer(
        f"Задача #{job.id}: файл получен.\n"
        "Выберите движок для тестовой расшифровки:",
        reply_markup=stt_provider_keyboard(job.id),
    )


@router.callback_query(F.data.startswith("stt_provider:"))
async def callback_stt_provider(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None or not callback.data:
        await callback.answer("Не удалось обработать запрос", show_alert=True)
        return

    try:
        _, raw_job_id, provider = callback.data.split(":", maxsplit=2)
        job_id = int(raw_job_id)
    except ValueError:
        await callback.answer("Некорректная команда", show_alert=True)
        return

    if provider not in {"yandex", "aitunnel", "neuroapi"}:
        await callback.answer("Неизвестный провайдер", show_alert=True)
        return
    if provider == "aitunnel" and not settings.aitunnel_api_key:
        await callback.answer("AI Tunnel API key не настроен на сервере", show_alert=True)
        return
    if provider == "neuroapi" and not settings.neuroapi_api_key:
        await callback.answer("NeuroAPI API key не настроен на сервере", show_alert=True)
        return

    job = await session.scalar(
        select(MediaProcessingJob).where(
            MediaProcessingJob.id == job_id,
            MediaProcessingJob.user_id == callback.from_user.id,
        )
    )
    if job is None:
        await callback.answer("Задача не найдена", show_alert=True)
        return
    if job.status != "awaiting_provider":
        await callback.answer("Провайдер для этой задачи уже выбран", show_alert=True)
        return

    job.stt_provider = provider
    job.status = "queued"
    await session.commit()

    provider_name = {
        "aitunnel": "AI Tunnel Whisper",
        "neuroapi": "NeuroAPI Whisper",
    }.get(provider, "Yandex")
    await callback.answer(f"Выбрано: {provider_name}")
    await callback.message.edit_reply_markup(reply_markup=None)
    await callback.message.answer(
        f"Задача #{job.id}: выбрано {provider_name}, файл поставлен в очередь.\n"
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
        provider = record.stt_provider or "yandex"
        lines.append(f"#{record.id}: {record.file_type}, {provider}, {len(record.transcript)} символов")
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

    participant_name: str | None = None
    exercise_name: str | None = None
    if record.exercise_id is not None:
        exercise = await session.get(Exercise, record.exercise_id)
        if exercise is not None:
            exercise_name = exercise.name
            participant = await session.get(Participant, exercise.participant_id)
            participant_name = participant.full_name if participant else None

    await message.answer(
        "Пересобираю файл расшифровки: очищаю повторы и заново размечаю роли"
        f"{f' по участнику {participant_name}' if participant_name else ''}..."
    )
    cleaned_transcript = normalize_transcript_text(record.raw_transcript or record.transcript)
    try:
        record.transcript = await label_transcript_roles(
            cleaned_transcript,
            assessed_participant_name=participant_name,
            exercise_name=exercise_name,
        )
    except RoleLabelingError as exc:
        await message.answer(
            f"Не удалось заново разметить роли, сохраню очищенный текст без новой разметки: {escape(str(exc), quote=False)}"
        )
        record.transcript = cleaned_transcript
    await session.commit()

    transcript_path = await build_transcript_text_file(transcript=record.transcript, record_id=record.id)
    record.transcript_file_path = str(transcript_path)
    await session.commit()

    await message.answer_document(
        FSInputFile(transcript_path, filename=transcript_path.name),
        caption=f"Обновлённая расшифровка записи #{record.id}",
    )
