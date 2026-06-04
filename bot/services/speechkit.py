from __future__ import annotations

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from difflib import SequenceMatcher
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


@dataclass(frozen=True)
class TranscriptSegment:
    text: str
    timestamp: str | None = None
    speaker_tag: str | None = None


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


def _detect_v3_container_audio_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    if suffix in ASYNC_MP3_EXTENSIONS:
        return "MP3"
    if suffix in SYNC_OGG_OPUS_EXTENSIONS:
        return "OGG_OPUS"
    if suffix in {".wav"}:
        return "WAV"
    raise SpeechKitError(
        "SpeechKit v3 поддерживает контейнеры MP3, Ogg Opus и WAV. "
        "Для этого файла нужна конвертация в MP3/Ogg/WAV."
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

    transcript = normalize_transcript_text(transcript)
    logger.info("SpeechKit transcript received, length=%s", len(transcript))
    return transcript


async def transcribe_file_async(file_path: Path, *, language_code: str = "ru-RU") -> str:
    """Upload a long audio file to Object Storage and recognize it via SpeechKit async API."""
    try:
        audio_url = await upload_file_for_speechkit(file_path)
    except ObjectStorageError as exc:
        raise SpeechKitError(str(exc)) from exc

    if settings.speechkit_async_api_version.lower() == "v3":
        try:
            return await _transcribe_file_async_v3(
                file_path=file_path,
                audio_url=audio_url,
                language_code=language_code,
            )
        except SpeechKitError:
            if not settings.speechkit_v3_fallback_to_v2:
                raise
            logger.exception("SpeechKit v3 failed, falling back to async v2")

    return await _transcribe_file_async_v2(
        file_path=file_path,
        audio_url=audio_url,
        language_code=language_code,
    )


async def _transcribe_file_async_v2(*, file_path: Path, audio_url: str, language_code: str) -> str:
    audio_encoding = _detect_async_audio_encoding(file_path)
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


async def _transcribe_file_async_v3(*, file_path: Path, audio_url: str, language_code: str) -> str:
    container_audio_type = _detect_v3_container_audio_type(file_path)
    operation_id = await _start_async_recognition_v3(
        audio_url=audio_url,
        container_audio_type=container_audio_type,
        language_code=language_code,
    )
    await _wait_async_operation(operation_id)
    recognition = await _get_async_recognition_v3(operation_id)
    transcript = _extract_transcript_v3(recognition)
    if not transcript:
        raise SpeechKitError("SpeechKit async v3 recognition returned an empty transcript")
    logger.info("SpeechKit async v3 transcript received, length=%s", len(transcript))
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


async def _start_async_recognition_v3(
    *,
    audio_url: str,
    container_audio_type: str,
    language_code: str,
) -> str:
    headers = _speechkit_headers()
    body: dict[str, Any] = {
        "uri": audio_url,
        "recognitionModel": {
            "model": settings.speechkit_v3_model,
            "audioFormat": {
                "containerAudio": {
                    "containerAudioType": container_audio_type,
                },
            },
            "textNormalization": {
                "textNormalization": "TEXT_NORMALIZATION_ENABLED",
                "profanityFilter": False,
                "literatureText": True,
                "phoneFormattingMode": "PHONE_FORMATTING_MODE_DISABLED",
            },
            "languageRestriction": {
                "restrictionType": "WHITELIST",
                "languageCode": [language_code],
            },
            "audioProcessingType": "FULL_DATA",
        },
    }
    if settings.speechkit_v3_enable_speaker_labeling:
        body["speakerLabeling"] = {"speakerLabeling": "SPEAKER_LABELING_ENABLED"}
        body["speechAnalysis"] = {
            "enableSpeakerAnalysis": True,
            "enableConversationAnalysis": True,
        }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            settings.speechkit_async_stt_v3_url,
            headers=headers,
            json=body,
            timeout=aiohttp.ClientTimeout(total=60),
        ) as response:
            payload = await response.json(content_type=None)

    if response.status >= 400:
        logger.error("SpeechKit async v3 start error %s: %s", response.status, payload)
        raise SpeechKitError(f"SpeechKit async v3 start returned HTTP {response.status}: {payload}")

    operation_id = payload.get("id")
    if not operation_id:
        raise SpeechKitError(f"SpeechKit async v3 start returned no operation id: {payload}")
    logger.info("SpeechKit async v3 operation started: %s", operation_id)
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


async def _get_async_recognition_v3(operation_id: str) -> Any:
    headers = _speechkit_headers()
    async with aiohttp.ClientSession() as session:
        async with session.get(
            settings.speechkit_async_stt_v3_result_url,
            params={"operationId": operation_id},
            headers=headers,
            timeout=aiohttp.ClientTimeout(total=180),
        ) as response:
            payload = await _read_json_or_json_lines(response)

    if response.status >= 400:
        logger.error("SpeechKit async v3 result error %s: %s", response.status, payload)
        raise SpeechKitError(f"SpeechKit async v3 result returned HTTP {response.status}: {payload}")
    return payload


async def _read_json_or_json_lines(response: aiohttp.ClientResponse) -> Any:
    text = await response.text()
    if not text.strip():
        return {}
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        items: list[Any] = []
        for line in text.splitlines():
            line = line.strip()
            if not line:
                continue
            items.append(json.loads(line))
        return items


def _speechkit_headers() -> dict[str, str]:
    return {
        "Authorization": f"Api-Key {settings.yandex_speechkit_api_key}",
        "Content-Type": "application/json",
        "x-folder-id": settings.yandex_folder_id,
    }


def _extract_transcript(operation: dict[str, Any]) -> str:
    segments = _extract_transcript_segments(operation)
    if settings.speechkit_deduplicate_transcript:
        segments = _deduplicate_segments(segments)
    return _format_transcript_segments(segments)


def _extract_transcript_v3(payload: Any) -> str:
    segments: list[TranscriptSegment] = []
    final_segments_by_index: dict[str, TranscriptSegment] = {}

    for event in _iter_v3_events(payload):
        final_payload = event.get("final")
        if isinstance(final_payload, dict):
            segment = _extract_v3_segment(event, final_payload)
            if segment is not None:
                final_index = str(event.get("audioCursors", {}).get("finalIndex") or len(final_segments_by_index))
                final_segments_by_index[final_index] = segment
                segments.append(segment)

        refinement_payload = event.get("finalRefinement")
        if isinstance(refinement_payload, dict):
            normalized = refinement_payload.get("normalizedText")
            if isinstance(normalized, dict):
                segment = _extract_v3_segment(event, normalized)
                final_index = str(refinement_payload.get("finalIndex") or event.get("audioCursors", {}).get("finalIndex") or "")
                if segment is not None:
                    if final_index and final_index in final_segments_by_index:
                        previous = final_segments_by_index[final_index]
                        refined = TranscriptSegment(
                            text=segment.text,
                            timestamp=segment.timestamp or previous.timestamp,
                            speaker_tag=segment.speaker_tag or previous.speaker_tag,
                        )
                        final_segments_by_index[final_index] = refined
                        try:
                            segments[segments.index(previous)] = refined
                        except ValueError:
                            segments.append(refined)
                    else:
                        segments.append(segment)

    if settings.speechkit_deduplicate_transcript:
        segments = _deduplicate_segments(segments)
    return _format_transcript_segments(segments)


def _iter_v3_events(payload: Any) -> list[dict[str, Any]]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    if any(key in payload for key in ("final", "finalRefinement", "partial", "speakerAnalysis")):
        return [payload]
    for key in ("result", "response", "responses", "chunks"):
        value = payload.get(key)
        if isinstance(value, list):
            return [item for item in value if isinstance(item, dict)]
    return []


def _extract_v3_segment(event: dict[str, Any], speech_payload: dict[str, Any]) -> TranscriptSegment | None:
    alternatives = speech_payload.get("alternatives") or []
    if not alternatives:
        return None
    alternative = alternatives[0]
    if not isinstance(alternative, dict):
        return None
    text = _clean_transcript_text(str(alternative.get("text", "")).strip())
    if not text:
        return None
    timestamp = _format_v3_timestamp(
        alternative.get("startTimeMs")
        or speech_payload.get("startTimeMs")
        or _first_v3_word_start_time(alternative)
    )
    speaker_tag = _find_speaker_tag(event, speech_payload, alternative)
    return TranscriptSegment(text=text, timestamp=timestamp, speaker_tag=speaker_tag)


def _find_speaker_tag(*items: Any) -> str | None:
    for item in items:
        if not isinstance(item, dict):
            continue
        for key in ("speakerTag", "speaker_tag", "channelTag", "channel_tag"):
            value = item.get(key)
            if value is not None and str(value) != "":
                return str(value)
        words = item.get("words") or []
        if words and isinstance(words[0], dict):
            tag = _find_speaker_tag(words[0])
            if tag:
                return tag
    return None


def _format_v3_timestamp(value: Any) -> str | None:
    if value is None:
        return None
    try:
        seconds = int(str(value)) / 1000
    except ValueError:
        return None
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    return f"{minutes:02d}:{rest:02d}"


def _first_v3_word_start_time(alternative: dict[str, Any]) -> Any:
    words = alternative.get("words") or []
    if not words:
        return None
    first_word = words[0]
    if not isinstance(first_word, dict):
        return None
    return first_word.get("startTimeMs") or first_word.get("start_time_ms")


def normalize_transcript_text(transcript: str) -> str:
    """Clean an already formatted transcript without calling SpeechKit again."""
    segments = [_parse_transcript_line(line) for line in transcript.splitlines()]
    segments = [segment for segment in segments if segment is not None]
    if settings.speechkit_deduplicate_transcript:
        segments = _deduplicate_segments(segments)
    return _format_transcript_segments(segments)


def _extract_transcript_segments(operation: dict[str, Any]) -> list[TranscriptSegment]:
    chunks = operation.get("response", {}).get("chunks", [])
    segments: list[TranscriptSegment] = []
    for chunk in chunks:
        alternatives = chunk.get("alternatives") or []
        if not alternatives:
            continue
        alternative = alternatives[0]
        text = _clean_transcript_text(str(alternative.get("text", "")).strip())
        if text:
            segments.append(TranscriptSegment(text=text, timestamp=_format_segment_timestamp(chunk, alternative)))
    return segments


def _deduplicate_segments(segments: list[TranscriptSegment]) -> list[TranscriptSegment]:
    cleaned: list[TranscriptSegment] = []
    threshold = settings.speechkit_dedup_similarity_threshold

    for segment in segments:
        normalized = _normalize_for_dedup(segment.text)
        if not normalized:
            continue

        duplicate_index = _find_recent_duplicate(cleaned, segment, normalized, threshold=threshold)
        if duplicate_index is None:
            cleaned.append(segment)
            continue

        existing = cleaned[duplicate_index]
        if len(_normalize_for_dedup(segment.text)) > len(_normalize_for_dedup(existing.text)):
            cleaned[duplicate_index] = TranscriptSegment(text=segment.text, timestamp=existing.timestamp or segment.timestamp)

    return cleaned


def _find_recent_duplicate(
    segments: list[TranscriptSegment],
    segment: TranscriptSegment,
    normalized_text: str,
    *,
    threshold: float,
    window_size: int = 4,
) -> int | None:
    for index in range(len(segments) - 1, max(-1, len(segments) - window_size - 1), -1):
        candidate = _normalize_for_dedup(segments[index].text)
        if not candidate:
            continue
        if _is_same_timestamp_duplicate(segments[index], segment, candidate, normalized_text):
            return index
        if candidate == normalized_text:
            return index
        if len(normalized_text) > 40 and (normalized_text in candidate or candidate in normalized_text):
            return index
        if _similarity(candidate, normalized_text) >= threshold:
            return index
    return None


def _is_same_timestamp_duplicate(
    existing: TranscriptSegment,
    current: TranscriptSegment,
    existing_normalized: str,
    current_normalized: str,
) -> bool:
    if not existing.timestamp or existing.timestamp != current.timestamp:
        return False
    if existing.speaker_tag and current.speaker_tag and existing.speaker_tag != current.speaker_tag:
        return False
    if len(existing_normalized) < 25 or len(current_normalized) < 25:
        return existing_normalized == current_normalized
    if existing_normalized in current_normalized or current_normalized in existing_normalized:
        return True
    if _word_overlap(existing_normalized, current_normalized) >= 0.65:
        return True
    return _similarity(existing_normalized, current_normalized) >= 0.55


def _format_transcript_segments(segments: list[TranscriptSegment]) -> str:
    parts: list[str] = []
    for segment in segments:
        speaker = f"{segment.speaker_tag}: " if segment.speaker_tag else ""
        if segment.timestamp:
            parts.append(f"[{segment.timestamp}] {speaker}{segment.text}")
        else:
            parts.append(f"{speaker}{segment.text}")
    return "\n".join(parts).strip()


def _clean_transcript_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    return text


def _parse_transcript_line(line: str) -> TranscriptSegment | None:
    line = _clean_transcript_text(line)
    if not line:
        return None
    match = re.match(
        r"^\[(?P<timestamp>\d{2}:\d{2}(?::\d{2})?)\]\s*(?:(?P<speaker>[^:]{1,64}):\s*)?(?P<text>.+)$",
        line,
    )
    if match:
        return TranscriptSegment(
            text=_clean_transcript_text(match.group("text")),
            timestamp=match.group("timestamp"),
            speaker_tag=match.group("speaker"),
        )
    return TranscriptSegment(text=line)


def _normalize_for_dedup(text: str) -> str:
    text = text.lower()
    text = re.sub(r"\[[0-9: ]+\]", " ", text)
    text = re.sub(r"[^0-9a-zа-яё]+", " ", text, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", text).strip()


def _similarity(left: str, right: str) -> float:
    return SequenceMatcher(a=left, b=right, autojunk=False).ratio()


def _word_overlap(left: str, right: str) -> float:
    left_words = set(left.split())
    right_words = set(right.split())
    if not left_words or not right_words:
        return 0.0
    return len(left_words & right_words) / min(len(left_words), len(right_words))


def _format_segment_timestamp(chunk: dict[str, Any], alternative: dict[str, Any]) -> str | None:
    start = (
        alternative.get("startTime")
        or alternative.get("start_time")
        or _first_word_start_time(alternative)
        or chunk.get("startTime")
        or chunk.get("start_time")
    )
    if not start:
        return None
    seconds = _duration_to_seconds(str(start))
    minutes = int(seconds // 60)
    rest = int(seconds % 60)
    return f"{minutes:02d}:{rest:02d}"


def _first_word_start_time(alternative: dict[str, Any]) -> str | None:
    words = alternative.get("words") or []
    if not words:
        return None
    first_word = words[0]
    if not isinstance(first_word, dict):
        return None
    return first_word.get("startTime") or first_word.get("start_time")


def _duration_to_seconds(value: str) -> float:
    value = value.strip().lower().removesuffix("s")
    try:
        return float(value)
    except ValueError:
        return 0.0
