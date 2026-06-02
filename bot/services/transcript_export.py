from __future__ import annotations

import logging
from pathlib import Path

from pydantic import BaseModel, Field, ValidationError

from bot.config import settings
from bot.services.yandex_gpt import YandexGPTError, complete_json

logger = logging.getLogger(__name__)


class RoleSegment(BaseModel):
    role: str
    timestamp: str | None = None
    text: str


class RoleBreakdown(BaseModel):
    summary: str
    segments: list[RoleSegment] = Field(default_factory=list)


async def build_transcript_text_file(*, transcript: str, record_id: int) -> Path:
    reports_dir = settings.download_dir.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / f"transcript_record_{record_id}.txt"

    role_text = await _build_role_breakdown_text(transcript)
    content = "\n\n".join(
        [
            f"Расшифровка записи #{record_id}",
            "Ролевая разметка",
            role_text,
            "Полный транскрипт",
            transcript,
        ]
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path


async def _build_role_breakdown_text(transcript: str) -> str:
    try:
        raw = await complete_json(
            system_prompt=_role_breakdown_system_prompt(),
            user_prompt=f"Транскрипт:\n\n{transcript}",
            json_schema=RoleBreakdown.model_json_schema(),
            temperature=0.05,
            max_tokens=8000,
        )
        breakdown = RoleBreakdown.model_validate(raw)
    except (YandexGPTError, ValidationError) as exc:
        logger.warning("Failed to build role breakdown, raw transcript will still be exported: %s", exc)
        return (
            "Ролевая разметка не была сформирована автоматически. "
            "Ниже сохранён полный транскрипт SpeechKit."
        )

    lines = [breakdown.summary.strip()]
    for segment in breakdown.segments:
        timestamp = f"[{segment.timestamp}] " if segment.timestamp else ""
        lines.append(f"{timestamp}{segment.role}: {segment.text}")
    return "\n".join(line for line in lines if line).strip()


def _role_breakdown_system_prompt() -> str:
    return """
Ты — ассистент HR-ассессмента. Нужно разметить транскрипт интервью или упражнения по ролям.

Правила:
1. Определи роли реплик: участник АЦ/оцениваемый, наблюдатель/ведущий, ролевой игрок, неизвестно.
2. Используй только текст транскрипта. Не придумывай реплики и факты.
3. Если роль неочевидна, ставь "неизвестно".
4. Сохраняй таймкоды, если они есть в транскрипте.
5. Не обязательно переписывать каждую короткую фразу отдельно: объединяй подряд идущие фрагменты одной роли.
6. Верни JSON по схеме.
""".strip()
