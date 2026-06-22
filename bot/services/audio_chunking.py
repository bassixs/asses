from __future__ import annotations

import asyncio
import logging
import math
import re
from dataclasses import dataclass
from pathlib import Path

from bot.config import settings

logger = logging.getLogger(__name__)


class AudioChunkingError(RuntimeError):
    pass


@dataclass(frozen=True)
class AudioChunk:
    path: Path
    index: int
    start_seconds: float
    duration_seconds: float


async def probe_duration_seconds(file_path: Path) -> float:
    """Return audio duration in seconds via ffprobe, falling back to ffmpeg."""
    duration = await _probe_with_ffprobe(file_path)
    if duration is not None:
        return duration

    duration = await _probe_with_ffmpeg(file_path)
    if duration is not None:
        return duration

    raise AudioChunkingError(f"Could not determine audio duration for {file_path}")


async def _probe_with_ffprobe(file_path: Path) -> float | None:
    try:
        process = await asyncio.create_subprocess_exec(
            settings.ffprobe_binary,
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(file_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        logger.warning("ffprobe binary not found: %s", settings.ffprobe_binary)
        return None

    stdout, _ = await process.communicate()
    if process.returncode != 0:
        return None
    raw = stdout.decode("utf-8", errors="replace").strip()
    try:
        value = float(raw)
    except ValueError:
        return None
    return value if value > 0 else None


_FFMPEG_TIME_RE = re.compile(r"time=(\d+):(\d{2}):(\d{2}(?:\.\d+)?)")


async def _probe_with_ffmpeg(file_path: Path) -> float | None:
    process = await asyncio.create_subprocess_exec(
        settings.ffmpeg_binary,
        "-i",
        str(file_path),
        "-f",
        "null",
        "-",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    _, stderr = await process.communicate()
    text = stderr.decode("utf-8", errors="replace")
    last_match: re.Match[str] | None = None
    for match in _FFMPEG_TIME_RE.finditer(text):
        last_match = match
    if last_match is None:
        return None
    hours, minutes, seconds = last_match.groups()
    total = int(hours) * 3600 + int(minutes) * 60 + float(seconds)
    return total if total > 0 else None


def compute_chunk_seconds(max_bytes: int, bitrate_kbps: int, safety: float) -> float:
    """How many seconds of audio fit under max_bytes at the given bitrate."""
    bytes_per_second = max(1.0, bitrate_kbps * 1000 / 8)
    usable_bytes = max_bytes * max(0.1, min(safety, 0.99))
    return usable_bytes / bytes_per_second


async def split_audio_into_chunks(file_path: Path, max_bytes: int, provider_name: str) -> list[AudioChunk]:
    """Split audio into overlapping chunks each expected to stay under max_bytes."""
    duration = await probe_duration_seconds(file_path)
    bitrate = settings.whisper_chunk_bitrate_kbps
    overlap = max(0, settings.whisper_chunk_overlap_seconds)

    chunk_seconds = compute_chunk_seconds(max_bytes, bitrate, settings.whisper_chunk_size_safety)
    # Cap by duration so each request finishes before the provider's gateway timeout (524),
    # not just under the size limit.
    if settings.whisper_chunk_max_seconds > 0:
        chunk_seconds = min(chunk_seconds, float(settings.whisper_chunk_max_seconds))
    chunk_seconds = max(chunk_seconds, float(settings.whisper_chunk_min_seconds))
    if chunk_seconds <= overlap:
        raise AudioChunkingError(
            f"Chunk length {chunk_seconds:.0f}s is not larger than overlap {overlap}s; "
            "lower WHISPER_CHUNK_OVERLAP_SECONDS or raise the bitrate budget",
        )

    step = chunk_seconds - overlap
    chunk_count = max(1, math.ceil((duration - overlap) / step)) if duration > chunk_seconds else 1

    logger.info(
        "Splitting audio for %s: duration=%.1fs chunk=%.1fs overlap=%ss count=%s bitrate=%sk",
        provider_name,
        duration,
        chunk_seconds,
        overlap,
        chunk_count,
        bitrate,
    )

    chunks: list[AudioChunk] = []
    for index in range(chunk_count):
        start = index * step
        if start >= duration:
            break
        length = min(chunk_seconds, duration - start + 0.5)
        output_path = _chunk_output_path(file_path, provider_name, index)
        await _extract_chunk(file_path, output_path, start, length, bitrate)
        size = output_path.stat().st_size if output_path.exists() else 0
        if size <= 0:
            raise AudioChunkingError(f"ffmpeg produced an empty chunk at {start:.0f}s for {provider_name}")
        if size > max_bytes:
            logger.warning(
                "Chunk %s for %s is %s bytes, above limit %s; provider may reject it",
                index,
                provider_name,
                size,
                max_bytes,
            )
        chunks.append(AudioChunk(path=output_path, index=index, start_seconds=start, duration_seconds=length))

    if not chunks:
        raise AudioChunkingError(f"No audio chunks were produced for {provider_name}")
    return chunks


def _chunk_output_path(file_path: Path, provider_name: str, index: int) -> Path:
    safe_provider = "".join(ch.lower() if ch.isalnum() else "_" for ch in provider_name).strip("_")
    return file_path.with_name(f"{file_path.stem}.{safe_provider}.chunk{index:03d}.mp3")


async def _extract_chunk(
    input_path: Path,
    output_path: Path,
    start_seconds: float,
    length_seconds: float,
    bitrate_kbps: int,
) -> None:
    process = await asyncio.create_subprocess_exec(
        settings.ffmpeg_binary,
        "-y",
        "-ss",
        f"{start_seconds:.3f}",
        "-t",
        f"{length_seconds:.3f}",
        "-i",
        str(input_path),
        "-vn",
        "-ac",
        "1",
        "-ar",
        "16000",
        "-b:a",
        f"{bitrate_kbps}k",
        str(output_path),
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    stdout, stderr = await process.communicate()
    if process.returncode != 0:
        error_text = stderr.decode("utf-8", errors="replace") or stdout.decode("utf-8", errors="replace")
        raise AudioChunkingError(f"ffmpeg chunk extraction failed with code {process.returncode}: {error_text[-1200:]}")


def cleanup_chunks(chunks: list[AudioChunk]) -> None:
    for chunk in chunks:
        try:
            chunk.path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete chunk file %s", chunk.path)


_WORD_RE = re.compile(r"\w+", re.UNICODE)


def merge_chunk_transcripts(parts: list[str]) -> str:
    """Join transcripts of overlapping chunks, trimming duplicated text at the seams."""
    cleaned = [part.strip() for part in parts if part and part.strip()]
    if not cleaned:
        return ""
    if len(cleaned) == 1:
        return cleaned[0]

    max_overlap_words = max(8, settings.whisper_chunk_overlap_seconds * 4)

    merged_words = _WORD_RE.findall(cleaned[0])
    result = cleaned[0]
    for part in cleaned[1:]:
        next_words = _WORD_RE.findall(part)
        trim = _overlap_word_count(merged_words, next_words, max_overlap_words)
        addition = _drop_leading_words(part, trim)
        if addition:
            result = f"{result}\n{addition}" if result else addition
        merged_words = (merged_words + next_words)[-(2 * max_overlap_words):]
    return result.strip()


def _normalize_word(word: str) -> str:
    return word.lower()


def _overlap_word_count(prev_words: list[str], next_words: list[str], max_overlap_words: int) -> int:
    limit = min(len(prev_words), len(next_words), max_overlap_words)
    prev_norm = [_normalize_word(w) for w in prev_words]
    next_norm = [_normalize_word(w) for w in next_words]
    for k in range(limit, 0, -1):
        if prev_norm[-k:] == next_norm[:k]:
            return k
    return 0


def _drop_leading_words(text: str, word_count: int) -> str:
    if word_count <= 0:
        return text.strip()
    consumed = 0
    for match in _WORD_RE.finditer(text):
        consumed += 1
        if consumed == word_count:
            return text[match.end():].lstrip(" \t,.;:-—\n").strip()
    return ""
