from __future__ import annotations

from pathlib import Path

from bot.config import settings
from bot.services.role_labeling import label_transcript_roles
from bot.services.speechkit import normalize_transcript_text


async def build_transcript_text_file(*, transcript: str, record_id: int) -> Path:
    reports_dir = settings.download_dir.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / f"transcript_record_{record_id}.txt"

    cleaned_transcript = normalize_transcript_text(transcript)
    if settings.role_labeling_enabled:
        cleaned_transcript = await label_transcript_roles(cleaned_transcript)

    content = "\n\n".join(
        [
            f"Расшифровка записи #{record_id}",
            cleaned_transcript,
        ]
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path
