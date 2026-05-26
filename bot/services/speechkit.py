from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

from bot.config import settings
from bot.services.object_storage import ObjectStorageError, upload_file_for_speechkit

logger = logging.getLogger(__name__)

SYNC_OGG_OPUS_EXTENSIONS = {".oga", ".ogg", ".opus"}
SYNC_LPCM_EXTENSIONS = {".lpcm", ".pcm", ".raw"}
ASYNC_MP3_EXTENSIONS = {".mp3"}
ASYNC_AUDIO_EXTENSIONS = SYNC_OGG_OPUS_EXTENSIONS | SYNC_LPCM_EXTENSIONS | ASYNC_MP3_EXTENSIONS


class SpeechKitError(RuntimeError):
    pass


def _detect_async_audio_encoding(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in SYNC_OGG_OPUS_EXTENSIONS:
        return "OGG_OPUS"
    if suffix in SYNC_LPCM_EXTENSIONS:
        return "LINEAR16_PCM"
    if suffix in ASYNC_MP3_EXTENSIONS:
        return "MP3"
    raise SpeechKitError(
        "Асинхронный SpeechKit v2 поддерживает Ogg Opus, MP3 и raw LPCM. "
        "Для WAV/M4A/документов нужна предварительная конвертация в MP3 или Ogg Opus."
    )


async def transcribe_file(file_path: Path, *, language_code: str = "ru-RU") -> str:
    """Transcribe a file using sync API for tiny clips and async API for long audio."""
    logger.info("Sending file to Yandex SpeechKit: %s", file_path)
    if not file_path.exists():
        raise SpeechKitError(f"File not found: {file_path}")

    file_size = file_path.stat().st_size
    if _can_use_sync_recognition(file_path, file_size):
        return await _transcribe_file_sync(file_path, language_code=language_code)

    return await transcribe_file_async(file_path, language_code=language_code)


def _can_use_sync_recognition(file_path: Path, file_size: int) -> bool:
    return file_size <= settings.speechkit_sync_max_bytes and file_path.suffix.lower() in (
        SYNC_OGG_OPUS_EXTENSIONS | SYNC_LPCM_EXTENSIONS
    )


async def _transcribe_file_sync(file_path: Path, *, language_code: str = "ru-RU") -> str:
    suffix = file_path.suffix.lower()
    if suffix in SYNC_OGG_OPUS_EXTENSIONS:
        audio_format = "oggopus"
    elif suffix in SYNC_LPCM_EXTENSIONS:
        audio_format = "lpcm"
    else:
        raise SpeechKitError(
            "Синхронный SpeechKit v1 поддерживает только Ogg Opus или raw LPCM. "
            "Конвертируйте файл в Ogg Opus или подключите асинхронное распознавание для аудиофайлов."
        )

    audio_bytes = file_path.read_bytes()

    headers = {"Authorization": f"Api-Key {settings.yandex_speechkit_api_key}"}
    params = {
        "folderId": settings.yandex_folder_id,
        "lang": language_code,
        "format": audio_format,
    }
    if audio_format == "lpcm":
        params["sampleRateHertz"] = "48000"

    async with aiohttp.ClientSession() as session:
        async with session.post(
            settings.speechkit_stt_url,
            params=params,
            headers=headers,
            data=audio_bytes,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as response:
            payload = await response.json(content_type=None)

    if response.status >= 400:
        logger.error("SpeechKit error %s: %s", response.status, payload)
        raise SpeechKitError(f"SpeechKit returned HTTP {response.status}: {payload}")

    transcript = str(payload.get("result", "")).strip()
    if not transcript:
        logger.warning("SpeechKit returned an empty transcript: %s", payload)
        raise SpeechKitError("SpeechKit returned an empty transcript")

    logger.info("SpeechKit transcript received, length=%s", len(transcript))
    return transcript


async def transcribe_file_async(file_path: Path, *, language_code: str = "ru-RU") -> str:
    """Upload a long audio file to Object Storage and recognize it via SpeechKit API v2."""
    audio_encoding = _detect_async_audio_encoding(file_path)
    try:
        audio_url = await upload_file_for_speechkit(file_path)
    except ObjectStorageError as exc:
        raise SpeechKitError(str(exc)) from exc
    operation_id = await _start_async_recognition(
        audio_url=audio_url,
        audio_encoding=audio_encoding,
        language_code=language_code,
    )
    operation = await _wait_async_operation(operation_id)
    transcript = _extract_transcript(operation)
    if not transcript:
        raise SpeechKitError("SpeechKit async recognition returned an empty transcript")
    logger.info("SpeechKit async transcript received, length=%s", len(transcript))
    return transcript


async def _start_async_recognition(
    *,
    audio_url: str,
    audio_encoding: str,
    language_code: str,
) -> str:
    headers = {
        "Authorization": f"Api-Key {settings.yandex_speechkit_api_key}",
        "Content-Type": "application/json",
    }
    specification: dict[str, Any] = {
        "languageCode": language_code,
        "model": "general",
        "profanityFilter": False,
        "literature_text": True,
        "audioEncoding": audio_encoding,
        "rawResults": False,
    }
    if audio_encoding == "LINEAR16_PCM":
        specification["sampleRateHertz"] = 48000
        specification["audioChannelCount"] = 1

    body = {
        "config": {"specification": specification},
        "audio": {"uri": audio_url},
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            settings.speechkit_async_stt_url,
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            payload = await response.json(content_type=None)

    if response.status >= 400:
        logger.error("SpeechKit async start error %s: %s", response.status, payload)
        raise SpeechKitError(f"SpeechKit async start returned HTTP {response.status}: {payload}")

    operation_id = payload.get("id")
    if not operation_id:
        raise SpeechKitError(f"SpeechKit async start returned no operation id: {payload}")
    logger.info("SpeechKit async operation started: %s", operation_id)
    return str(operation_id)


async def _wait_async_operation(operation_id: str) -> dict[str, Any]:
    headers = {"Authorization": f"Api-Key {settings.yandex_speechkit_api_key}"}
    deadline = asyncio.get_running_loop().time() + settings.speechkit_async_timeout_seconds

    async with aiohttp.ClientSession() as session:
        while True:
            async with session.get(
                f"{settings.yandex_operation_url}/{operation_id}",
                headers=headers,
                timeout=aiohttp.ClientTimeout(total=60),
            ) as response:
                payload = await response.json(content_type=None)

            if response.status >= 400:
                logger.error("SpeechKit operation error %s: %s", response.status, payload)
                raise SpeechKitError(f"SpeechKit operation returned HTTP {response.status}: {payload}")

            if payload.get("done"):
                if "error" in payload:
                    raise SpeechKitError(f"SpeechKit async recognition failed: {payload['error']}")
                return payload

            if asyncio.get_running_loop().time() >= deadline:
                raise SpeechKitError(f"SpeechKit async recognition timed out: operation_id={operation_id}")

            await asyncio.sleep(settings.speechkit_async_poll_interval_seconds)


def _extract_transcript(operation: dict[str, Any]) -> str:
    chunks = operation.get("response", {}).get("chunks", [])
    parts: list[str] = []
    for chunk in chunks:
        alternatives = chunk.get("alternatives") or []
        if not alternatives:
            continue
        text = str(alternatives[0].get("text", "")).strip()
        if text:
            timestamp = _format_chunk_timestamp(chunk)
            parts.append(f"[{timestamp}] {text}" if timestamp else text)
    return "\n".join(parts).strip()


def _format_chunk_timestamp(chunk: dict[str, Any]) -> str | None:
    start = chunk.get("startTime") or chunk.get("start_time")
    if not start:
        return None
    seconds = _duration_to_seconds(str(start))
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    return f"{minutes:02d}:{rest:02d}"


def _duration_to_seconds(value: str) -> float:
    value = value.strip().lower().removesuffix("s")
    try:
        return float(value)
    except ValueError:
        return 0.0
