from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

from bot.config import settings
from bot.services.speechkit import normalize_transcript_text

logger = logging.getLogger(__name__)


class NeuroAPIWhisperError(RuntimeError):
    pass


async def transcribe_file_neuroapi_whisper(file_path: Path) -> str:
    if not settings.neuroapi_api_key:
        raise NeuroAPIWhisperError("NeuroAPI key is not configured")
    if not file_path.exists():
        raise NeuroAPIWhisperError(f"File not found: {file_path}")

    timeout = aiohttp.ClientTimeout(total=settings.neuroapi_timeout_seconds)
    headers = {"Authorization": f"Bearer {settings.neuroapi_api_key}"}
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            payload = await _send_transcription_request(session, file_path)
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise NeuroAPIWhisperError(f"NeuroAPI Whisper network error: {exc}") from exc

    transcript = _extract_transcript_text(payload)
    if not transcript:
        raise NeuroAPIWhisperError(f"NeuroAPI Whisper returned an empty transcript: {payload}")
    transcript = normalize_transcript_text(transcript)
    logger.info("NeuroAPI Whisper transcript received, length=%s", len(transcript))
    return transcript


async def _send_transcription_request(session: aiohttp.ClientSession, file_path: Path) -> dict[str, Any]:
    url = f"{settings.neuroapi_base_url.rstrip('/')}/audio/transcriptions"
    form = aiohttp.FormData()
    form.add_field("model", settings.neuroapi_whisper_model)
    if settings.neuroapi_language:
        form.add_field("language", settings.neuroapi_language)
    if settings.neuroapi_response_format:
        form.add_field("response_format", settings.neuroapi_response_format)

    with file_path.open("rb") as audio_file:
        form.add_field(
            "file",
            audio_file,
            filename=file_path.name,
            content_type=_guess_content_type(file_path),
        )
        async with session.post(url, data=form) as response:
            payload = await _read_response(response)
            if response.status >= 400:
                raise NeuroAPIWhisperError(f"NeuroAPI Whisper returned HTTP {response.status}: {payload}")
            return payload


async def _read_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        payload = await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return {"text": await response.text()}
    if isinstance(payload, dict):
        return payload
    return {"payload": payload}


def _extract_transcript_text(payload: dict[str, Any]) -> str:
    text = payload.get("text")
    if isinstance(text, str):
        return text.strip()

    segments = payload.get("segments")
    if isinstance(segments, list):
        parts: list[str] = []
        for segment in segments:
            if isinstance(segment, dict) and isinstance(segment.get("text"), str):
                parts.append(segment["text"].strip())
        return "\n".join(part for part in parts if part).strip()

    payload_text = payload.get("payload")
    if isinstance(payload_text, str):
        return payload_text.strip()
    return ""


def _guess_content_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix == ".mp3":
        return "audio/mpeg"
    if suffix in {".ogg", ".oga", ".opus"}:
        return "audio/ogg"
    if suffix == ".wav":
        return "audio/wav"
    return "application/octet-stream"
