from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from dataclasses import dataclass
from html import escape
from pathlib import Path

from aiogram import Bot
from sqlalchemy import select

from bot.config import settings
from bot.database import async_session_maker
from bot.keyboards import transcript_actions_keyboard
from bot.models import InterviewRecord, MediaProcessingJob
from bot.services.audio_chunking import merge_chunk_transcripts
from bot.services.audio_preprocessing import (
    AudioPreprocessingError,
    prepare_audio_chunks_for_upload,
    prepare_audio_for_upload,
)
from bot.services.aitunnel_whisper import AITunnelWhisperError, transcribe_file_aitunnel_whisper
from bot.services.neuroapi_whisper import NeuroAPIWhisperError, transcribe_file_neuroapi_whisper
from bot.services.role_labeling import RoleLabelingError, label_transcript_roles
from bot.services.speechkit import SpeechKitError, transcribe_file
from bot.services.telegram_files import download_telegram_file
from bot.services.transcript_export import build_transcript_text_file

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class ClaimedMediaJob:
    id: int
    chat_id: int
    user_id: int
    file_id: str
    file_unique_id: str | None
    file_type: str
    file_name: str | None
    stt_provider: str


def start_media_job_worker(bot: Bot) -> asyncio.Task[None]:
    return asyncio.create_task(_media_job_worker_loop(bot), name="media-job-worker")


async def _media_job_worker_loop(bot: Bot) -> None:
    logger.info("Media job worker started")
    await _requeue_interrupted_jobs()
    while True:
        try:
            job = await _claim_next_job()
            if job is None:
                await asyncio.sleep(3)
                continue
            await _process_job(bot, job.id)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Media job worker iteration failed")
            await asyncio.sleep(5)


async def _claim_next_job() -> ClaimedMediaJob | None:
    async with async_session_maker() as session:
        job = await session.scalar(
            select(MediaProcessingJob)
            .where(MediaProcessingJob.status == "queued")
            .order_by(MediaProcessingJob.created_at)
            .limit(1)
        )
        if job is None:
            return None

        job.status = "processing"
        job.started_at = datetime.now(timezone.utc)
        await session.commit()
        return ClaimedMediaJob(
            id=job.id,
            chat_id=job.chat_id,
            user_id=job.user_id,
            file_id=job.file_id,
            file_unique_id=job.file_unique_id,
            file_type=job.file_type,
            file_name=job.file_name,
            stt_provider=job.stt_provider or "yandex",
        )


async def _requeue_interrupted_jobs() -> None:
    async with async_session_maker() as session:
        jobs = list(
            await session.scalars(
                select(MediaProcessingJob)
                .where(MediaProcessingJob.status == "processing")
                .order_by(MediaProcessingJob.started_at)
            )
        )
        for job in jobs:
            job.status = "queued"
            job.error_message = "Возвращено в очередь после перезапуска worker."
        if jobs:
            logger.warning("Requeued interrupted media jobs: count=%s", len(jobs))
            await session.commit()


async def _process_job(bot: Bot, job_id: int) -> None:
    job = await _load_claimed_job(job_id)
    if job is None:
        return

    try:
        await bot.send_message(job.chat_id, f"Задача #{job.id}: скачиваю файл из Telegram...")
        local_path = await download_telegram_file(bot, job.file_id, job.file_type, job.file_name)

        provider_name = _provider_name(job.stt_provider)
        await bot.send_message(job.chat_id, f"Задача #{job.id}: отправляю аудио на расшифровку через {provider_name}...")
        raw_transcript = await _transcribe_with_provider(bot, job, local_path, job.stt_provider)
        transcript = await _label_roles_or_keep_raw(bot, job, raw_transcript)

        record_id = await _create_record(job, local_path, raw_transcript, transcript)
        transcript_path = await build_transcript_text_file(transcript=transcript, record_id=record_id)
        await _mark_completed(job.id, record_id, transcript_path)

        await bot.send_message(
            job.chat_id,
            f"Задача #{job.id}: расшифровано через {provider_name}.\n"
            f"ID записи: {record_id}\n"
            f"Напишите /assess {record_id} для оценки по компетенциям.",
            reply_markup=transcript_actions_keyboard(record_id),
        )
    except SpeechKitError as exc:
        await _mark_failed(job_id, str(exc))
        logger.exception("SpeechKit failed for media job id=%s", job_id)
        await bot.send_message(job.chat_id, f"Задача #{job.id}: не удалось расшифровать запись: {escape(str(exc), quote=False)}")
    except AITunnelWhisperError as exc:
        await _mark_failed(job_id, str(exc))
        logger.exception("AI Tunnel Whisper failed for media job id=%s", job_id)
        await bot.send_message(job.chat_id, f"Задача #{job.id}: AI Tunnel Whisper не смог расшифровать запись: {escape(str(exc), quote=False)}")
    except NeuroAPIWhisperError as exc:
        await _mark_failed(job_id, str(exc))
        logger.exception("NeuroAPI Whisper failed for media job id=%s", job_id)
        await bot.send_message(job.chat_id, f"Задача #{job.id}: NeuroAPI Whisper не смог расшифровать запись: {escape(str(exc), quote=False)}")
    except AudioPreprocessingError as exc:
        await _mark_failed(job_id, str(exc))
        logger.exception("Audio preprocessing failed for media job id=%s", job_id)
        await bot.send_message(job.chat_id, f"Задача #{job.id}: не удалось подготовить аудио для Whisper: {escape(str(exc), quote=False)}")
    except Exception as exc:
        await _mark_failed(job_id, str(exc))
        logger.exception("Media job failed id=%s", job_id)
        await bot.send_message(job.chat_id, f"Задача #{job.id}: произошла ошибка при обработке файла.")


async def _create_record(job: ClaimedMediaJob, local_path: Path, raw_transcript: str, transcript: str) -> int:
    async with async_session_maker() as session:
        record = InterviewRecord(
            chat_id=job.chat_id,
            user_id=job.user_id,
            file_id=job.file_id,
            file_unique_id=job.file_unique_id,
            file_type=job.file_type,
            file_path=str(local_path),
            stt_provider=job.stt_provider,
            raw_transcript=raw_transcript,
            transcript=transcript,
        )
        session.add(record)
        await session.commit()
        await session.refresh(record)
        return record.id


async def _mark_completed(job_id: int, record_id: int, transcript_path: Path) -> None:
    async with async_session_maker() as session:
        record = await session.get(InterviewRecord, record_id)
        job = await session.get(MediaProcessingJob, job_id)
        if record is not None:
            record.transcript_file_path = str(transcript_path)
        if job is not None:
            job.record_id = record_id
            job.status = "completed"
            job.finished_at = datetime.now(timezone.utc)
        await session.commit()


async def _load_claimed_job(job_id: int) -> ClaimedMediaJob | None:
    async with async_session_maker() as session:
        job = await session.get(MediaProcessingJob, job_id)
        if job is None:
            return None
        return ClaimedMediaJob(
            id=job.id,
            chat_id=job.chat_id,
            user_id=job.user_id,
            file_id=job.file_id,
            file_unique_id=job.file_unique_id,
            file_type=job.file_type,
            file_name=job.file_name,
            stt_provider=job.stt_provider or "yandex",
        )


async def _transcribe_with_provider(bot: Bot, job: ClaimedMediaJob, local_path: Path, provider: str) -> str:
    if provider == "aitunnel":
        # AI Tunnel enforces a hard 25 MB per-request limit, so long audio is chunked.
        return await _transcribe_aitunnel_chunked(bot, job, local_path)
    if provider == "neuroapi":
        upload_path = await prepare_audio_for_upload(
            local_path,
            max_bytes=settings.neuroapi_max_upload_bytes,
            provider_name="neuroapi",
        )
        return await transcribe_file_neuroapi_whisper(upload_path)
    return await transcribe_file(local_path)


async def _transcribe_aitunnel_chunked(bot: Bot, job: ClaimedMediaJob, local_path: Path) -> str:
    parts = await prepare_audio_chunks_for_upload(
        local_path,
        max_bytes=settings.aitunnel_max_upload_bytes,
        provider_name="aitunnel",
    )
    if len(parts) == 1:
        return await transcribe_file_aitunnel_whisper(parts[0])

    await bot.send_message(
        job.chat_id,
        f"Задача #{job.id}: запись длинная, разбил на {len(parts)} частей и расшифрую по очереди.",
    )
    transcripts: list[str] = []
    for index, part in enumerate(parts, start=1):
        await bot.send_message(job.chat_id, f"Задача #{job.id}: расшифровываю часть {index}/{len(parts)}...")
        transcripts.append(await transcribe_file_aitunnel_whisper(part))
    return merge_chunk_transcripts(transcripts)


async def _label_roles_or_keep_raw(bot: Bot, job: ClaimedMediaJob, transcript: str) -> str:
    if not settings.role_labeling_enabled:
        return transcript

    try:
        await bot.send_message(job.chat_id, f"Задача #{job.id}: размечаю роли ведущий/участник...")
        return await label_transcript_roles(transcript)
    except RoleLabelingError as exc:
        logger.exception("Role labeling failed for media job id=%s", job.id)
        await bot.send_message(
            job.chat_id,
            f"Задача #{job.id}: расшифровка готова, но роли не удалось разметить: {escape(str(exc), quote=False)}",
        )
        return transcript


def _provider_name(provider: str) -> str:
    if provider == "aitunnel":
        return "AI Tunnel Whisper"
    if provider == "neuroapi":
        return "NeuroAPI Whisper"
    return "Yandex"


async def _mark_failed(job_id: int, error_message: str) -> None:
    async with async_session_maker() as session:
        job = await session.get(MediaProcessingJob, job_id)
        if job is None:
            return
        job.status = "failed"
        job.error_message = error_message[:4000]
        job.finished_at = datetime.now(timezone.utc)
        await session.commit()
