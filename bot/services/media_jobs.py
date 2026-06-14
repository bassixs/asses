from __future__ import annotations

import asyncio
import json
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
from bot.models import Exercise, InterviewRecord, MediaProcessingJob, Participant
from bot.services.audio_chunking import merge_chunk_transcripts
from bot.services.audio_preprocessing import (
    AudioPreprocessingError,
    prepare_audio_chunks_for_upload,
    prepare_audio_for_upload,
)
from bot.services.aitunnel_whisper import (
    AITunnelWhisperError,
    transcribe_aitunnel_with_segments,
)
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
    exercise_id: int | None = None


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
            stt_provider=job.stt_provider or "aitunnel",
            exercise_id=job.exercise_id,
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
        raw_transcript, segments = await _transcribe_with_provider(bot, job, local_path, job.stt_provider)

        participant_name, exercise_name = await _exercise_context(job.exercise_id)
        transcript = await _label_roles_or_keep_raw(bot, job, raw_transcript, participant_name, exercise_name)

        record_id = await _create_record(job, local_path, raw_transcript, transcript, segments)
        transcript_path = await build_transcript_text_file(transcript=transcript, record_id=record_id)
        await _mark_completed(job.id, record_id, transcript_path)

        if job.exercise_id is not None:
            await bot.send_message(
                job.chat_id,
                f"✅ Расшифровка готова (запись #{record_id}) и привязана к упражнению.\n"
                "Теперь отправьте блокнот наблюдателя по этому упражнению (.xlsx) 📊",
                reply_markup=transcript_actions_keyboard(record_id),
            )
        else:
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


async def _exercise_context(exercise_id: int | None) -> tuple[str | None, str | None]:
    if exercise_id is None:
        return None, None
    async with async_session_maker() as session:
        exercise = await session.get(Exercise, exercise_id)
        if exercise is None:
            return None, None
        participant = await session.get(Participant, exercise.participant_id)
        return (participant.full_name if participant else None), exercise.name


async def _create_record(
    job: ClaimedMediaJob,
    local_path: Path,
    raw_transcript: str,
    transcript: str,
    segments: list[dict[str, object]],
) -> int:
    async with async_session_maker() as session:
        record = InterviewRecord(
            chat_id=job.chat_id,
            user_id=job.user_id,
            exercise_id=job.exercise_id,
            file_id=job.file_id,
            file_unique_id=job.file_unique_id,
            file_type=job.file_type,
            file_path=str(local_path),
            stt_provider=job.stt_provider,
            raw_transcript=raw_transcript,
            transcript=transcript,
            transcript_segments=json.dumps(segments, ensure_ascii=False) if segments else None,
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
            stt_provider=job.stt_provider or "aitunnel",
            exercise_id=job.exercise_id,
        )


async def _transcribe_with_provider(
    bot: Bot,
    job: ClaimedMediaJob,
    local_path: Path,
    provider: str,
) -> tuple[str, list[dict[str, object]]]:
    if provider == "aitunnel":
        # AI Tunnel enforces a hard 25 MB per-request limit, so long audio is chunked.
        return await _transcribe_aitunnel_chunked(bot, job, local_path)
    if provider == "neuroapi":
        upload_path = await prepare_audio_for_upload(
            local_path,
            max_bytes=settings.neuroapi_max_upload_bytes,
            provider_name="neuroapi",
        )
        return await transcribe_file_neuroapi_whisper(upload_path), []
    return await transcribe_file(local_path), []


async def _transcribe_aitunnel_chunked(
    bot: Bot,
    job: ClaimedMediaJob,
    local_path: Path,
) -> tuple[str, list[dict[str, object]]]:
    parts = await prepare_audio_chunks_for_upload(
        local_path,
        max_bytes=settings.aitunnel_max_upload_bytes,
        provider_name="aitunnel",
    )
    if len(parts) == 1:
        path, offset = parts[0]
        text, segments = await transcribe_aitunnel_with_segments(path)
        return text, _offset_segments(segments, offset)

    await bot.send_message(
        job.chat_id,
        f"Задача #{job.id}: запись длинная, разбил на {len(parts)} частей и расшифрую по очереди.",
    )
    transcripts: list[str] = []
    all_segments: list[dict[str, object]] = []
    for index, (path, offset) in enumerate(parts, start=1):
        await bot.send_message(job.chat_id, f"Задача #{job.id}: расшифровываю часть {index}/{len(parts)}...")
        text, segments = await transcribe_aitunnel_with_segments(path)
        transcripts.append(text)
        all_segments.extend(_offset_segments(segments, offset))
    return merge_chunk_transcripts(transcripts), all_segments


def _offset_segments(segments: list[dict[str, object]], offset: float) -> list[dict[str, object]]:
    if not offset:
        return segments
    return [{"start": float(seg["start"]) + offset, "text": seg["text"]} for seg in segments]


async def _label_roles_or_keep_raw(
    bot: Bot,
    job: ClaimedMediaJob,
    transcript: str,
    assessed_participant_name: str | None = None,
    exercise_name: str | None = None,
) -> str:
    if not settings.role_labeling_enabled:
        return transcript

    try:
        await bot.send_message(job.chat_id, f"Задача #{job.id}: размечаю роли ведущий/участник...")
        return await label_transcript_roles(
            transcript,
            assessed_participant_name=assessed_participant_name,
            exercise_name=exercise_name,
        )
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
