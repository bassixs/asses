from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

import aiohttp

from bot.config import settings

logger = logging.getLogger(__name__)


class AssemblyAIError(RuntimeError):
    pass


async def transcribe_file_assemblyai(file_path: Path) -> str:
    if not settings.assemblyai_api_key:
        raise AssemblyAIError("AssemblyAI API key is not configured")
    if not file_path.exists():
        raise AssemblyAIError(f"File not found: {file_path}")

    timeout = aiohttp.ClientTimeout(total=None, sock_connect=60, sock_read=300)
    headers = {"Authorization": settings.assemblyai_api_key}
    async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
        audio_url = await _upload_file(session, file_path)
        transcript_id = await _submit_transcript(session, audio_url)
        payload = await _poll_transcript(session, transcript_id)

    transcript = _format_transcript(payload)
    if not transcript:
        raise AssemblyAIError("AssemblyAI returned an empty transcript")
    logger.info("AssemblyAI transcript received, length=%s", len(transcript))
    return transcript


async def _upload_file(session: aiohttp.ClientSession, file_path: Path) -> str:
    url = f"{settings.assemblyai_base_url.rstrip('/')}/v2/upload"
    with file_path.open("rb") as audio_file:
        async with session.post(
            url,
            data=audio_file,
            headers={
                "Authorization": settings.assemblyai_api_key,
                "Content-Type": "application/octet-stream",
            },
        ) as response:
            payload = await _read_json(response)
            if response.status >= 400:
                raise AssemblyAIError(f"AssemblyAI upload returned HTTP {response.status}: {payload}")

    upload_url = payload.get("upload_url")
    if not upload_url:
        raise AssemblyAIError(f"AssemblyAI upload returned no upload_url: {payload}")
    return str(upload_url)


async def _submit_transcript(session: aiohttp.ClientSession, audio_url: str) -> str:
    url = f"{settings.assemblyai_base_url.rstrip('/')}/v2/transcript"
    body: dict[str, Any] = {
        "audio_url": audio_url,
        "speech_models": settings.assemblyai_speech_model_list,
        "speaker_labels": settings.assemblyai_speaker_labels,
        "punctuate": True,
        "format_text": True,
    }
    if settings.assemblyai_language_code:
        body["language_code"] = settings.assemblyai_language_code

    async with session.post(url, json=body) as response:
        payload = await _read_json(response)
        if response.status >= 400:
            raise AssemblyAIError(f"AssemblyAI transcript start returned HTTP {response.status}: {payload}")

    transcript_id = payload.get("id")
    if not transcript_id:
        raise AssemblyAIError(f"AssemblyAI transcript start returned no id: {payload}")
    logger.info("AssemblyAI transcript started: %s", transcript_id)
    return str(transcript_id)


async def _poll_transcript(session: aiohttp.ClientSession, transcript_id: str) -> dict[str, Any]:
    url = f"{settings.assemblyai_base_url.rstrip('/')}/v2/transcript/{transcript_id}"
    started_at = asyncio.get_running_loop().time()
    while True:
        async with session.get(url) as response:
            payload = await _read_json(response)
            if response.status >= 400:
                raise AssemblyAIError(f"AssemblyAI transcript poll returned HTTP {response.status}: {payload}")

        status = str(payload.get("status", "")).lower()
        if status == "completed":
            return payload
        if status == "error":
            raise AssemblyAIError(str(payload.get("error") or "AssemblyAI transcription failed"))
        if asyncio.get_running_loop().time() - started_at > settings.assemblyai_timeout_seconds:
            raise AssemblyAIError(f"AssemblyAI transcription timed out: transcript_id={transcript_id}")
        await asyncio.sleep(settings.assemblyai_poll_interval_seconds)


async def _read_json(response: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        payload = await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return {"text": await response.text()}
    if not isinstance(payload, dict):
        return {"payload": payload}
    return payload


def _format_transcript(payload: dict[str, Any]) -> str:
    utterances = payload.get("utterances")
    if isinstance(utterances, list) and utterances:
        parts: list[str] = []
        for utterance in utterances:
            if not isinstance(utterance, dict):
                continue
            text = str(utterance.get("text") or "").strip()
            if not text:
                continue
            speaker = str(utterance.get("speaker") or "unknown").strip()
            timestamp = _format_ms_timestamp(utterance.get("start"))
            speaker_tag = f"speaker_{speaker}"
            if timestamp:
                parts.append(f"[{timestamp}] {speaker_tag}: {text}")
            else:
                parts.append(f"{speaker_tag}: {text}")
        return "\n".join(parts).strip()

    return str(payload.get("text") or "").strip()


def _format_ms_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        seconds = float(value) / 1000
    except (TypeError, ValueError):
        return None
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    return f"{minutes:02d}:{rest:02d}"
