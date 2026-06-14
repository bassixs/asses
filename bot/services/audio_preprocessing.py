from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from bot.config import settings
from bot.services.audio_chunking import AudioChunk, split_audio_into_chunks

logger = logging.getLogger(__name__)


class AudioPreprocessingError(RuntimeError):
    pass


async def prepare_audio_for_upload(file_path: Path, max_bytes: int, provider_name: str) -> Path:
    """Compress audio to fit under max_bytes. Used by providers without chunking."""
    if not file_path.exists():
        raise AudioPreprocessingError(f"File not found: {file_path}")

    original_size = file_path.stat().st_size
    if original_size <= max_bytes:
        return file_path

    bitrates = _parse_bitrates(settings.whisper_compression_bitrates_kbps)
    if not bitrates:
        raise AudioPreprocessingError("No valid Whisper compression bitrates configured")

    logger.info(
        "Preparing audio for %s: original_size=%s max_bytes=%s bitrates=%s",
        provider_name,
        original_size,
        max_bytes,
        bitrates,
    )

    last_error = ""
    for bitrate in bitrates:
        output_path = _compressed_output_path(file_path, provider_name, bitrate)
        await _run_ffmpeg(file_path, output_path, bitrate)
        compressed_size = output_path.stat().st_size if output_path.exists() else 0
        logger.info(
            "Compressed audio for %s: bitrate=%sk size=%s path=%s",
            provider_name,
            bitrate,
            compressed_size,
            output_path,
        )
        if 0 < compressed_size <= max_bytes:
            return output_path
        last_error = f"compressed size at {bitrate}k is {compressed_size} bytes"

    raise AudioPreprocessingError(
        f"Could not prepare audio under {max_bytes} bytes for {provider_name}: {last_error}",
    )


async def prepare_audio_chunks_for_upload(
    file_path: Path,
    max_bytes: int,
    provider_name: str,
) -> list[tuple[Path, float]]:
    """Return upload-ready audio parts as (path, start_offset_seconds).

    The offset is the part's start time in the original recording (0.0 for a single
    file or a whole-file compression), used to turn chunk-relative STT timestamps into
    absolute ones. Returns a single element when the file fits as-is or after whole-file
    compression, and multiple overlapping chunks otherwise. Used by AI Tunnel (25 MB limit).
    """
    if not file_path.exists():
        raise AudioPreprocessingError(f"File not found: {file_path}")

    original_size = file_path.stat().st_size
    if original_size <= max_bytes:
        return [(file_path, 0.0)]

    bitrates = _parse_bitrates(settings.whisper_compression_bitrates_kbps)
    if not bitrates:
        raise AudioPreprocessingError("No valid Whisper compression bitrates configured")

    logger.info(
        "Preparing audio for %s: original_size=%s max_bytes=%s bitrates=%s",
        provider_name,
        original_size,
        max_bytes,
        bitrates,
    )

    smallest_size = 0
    for bitrate in bitrates:
        output_path = _compressed_output_path(file_path, provider_name, bitrate)
        await _run_ffmpeg(file_path, output_path, bitrate)
        compressed_size = output_path.stat().st_size if output_path.exists() else 0
        logger.info(
            "Compressed audio for %s: bitrate=%sk size=%s path=%s",
            provider_name,
            bitrate,
            compressed_size,
            output_path,
        )
        if 0 < compressed_size <= max_bytes:
            return [(output_path, 0.0)]
        smallest_size = compressed_size

    if not settings.whisper_chunk_enabled:
        raise AudioPreprocessingError(
            f"Audio still {smallest_size} bytes after compression (limit {max_bytes}) "
            f"for {provider_name} and chunking is disabled",
        )

    try:
        chunks: list[AudioChunk] = await split_audio_into_chunks(file_path, max_bytes, provider_name)
    except Exception as exc:  # noqa: BLE001 - re-wrap into the preprocessing error type
        raise AudioPreprocessingError(f"Could not split audio into chunks for {provider_name}: {exc}") from exc
    return [(chunk.path, chunk.start_seconds) for chunk in chunks]


def _parse_bitrates(raw_value: str) -> list[int]:
    bitrates: list[int] = []
    for part in raw_value.split(","):
        try:
            bitrate = int(part.strip())
        except ValueError:
            continue
        if bitrate > 0:
            bitrates.append(bitrate)
    return bitrates


def _compressed_output_path(file_path: Path, provider_name: str, bitrate: int) -> Path:
    safe_provider = "".join(ch.lower() if ch.isalnum() else "_" for ch in provider_name).strip("_")
    return file_path.with_name(f"{file_path.stem}.{safe_provider}.{bitrate}k.mp3")


async def _run_ffmpeg(input_path: Path, output_path: Path, bitrate_kbps: int) -> None:
    process = await asyncio.create_subprocess_exec(
        settings.ffmpeg_binary,
        "-y",
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
        raise AudioPreprocessingError(f"ffmpeg failed with code {process.returncode}: {error_text[-1200:]}")
