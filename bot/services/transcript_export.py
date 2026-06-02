from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from bot.config import settings
from bot.services.yandex_gpt import YandexGPTError, complete_json

logger = logging.getLogger(__name__)

RoleName = Literal["участник АЦ/оцениваемый", "наблюдатель/ведущий", "ролевой игрок", "неизвестно"]


class RoleSegment(BaseModel):
    role: RoleName
    timestamp: str | None = None
    text: str
    confidence: float = Field(ge=0, le=1)


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
            (
                "Важно: роли определены автоматически по тексту. "
                "Если в аудио голоса похожи или SpeechKit распознал фразы с ошибками, разметку нужно проверить вручную."
            ),
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

    lines = [f"Кратко: {breakdown.summary.strip()}"] if breakdown.summary.strip() else []
    for segment in breakdown.segments:
        timestamp = f"[{segment.timestamp}] " if segment.timestamp else ""
        confidence = f" (уверенность {segment.confidence:.0%})" if segment.confidence < 0.8 else ""
        lines.append(f"{timestamp}{segment.role}{confidence}: {segment.text.strip()}")
    return "\n".join(line for line in lines if line).strip()


def _role_breakdown_system_prompt() -> str:
    return """
Ты — ассистент HR-ассессмента. Нужно разметить транскрипт интервью или упражнения по ролям.

Правила:
1. Используй только текст транскрипта. Не исправляй смысл, не придумывай реплики и факты.
2. Доступные роли строго такие: "участник АЦ/оцениваемый", "наблюдатель/ведущий", "ролевой игрок", "неизвестно".
3. "наблюдатель/ведущий" обычно задаёт вопросы, объясняет упражнение, даёт инструкции, завершает этап.
4. "участник АЦ/оцениваемый" обычно отвечает от первого лица, рассказывает о своих задачах, решениях, трудностях, мотивации.
5. "ролевой игрок" обычно находится внутри деловой ситуации упражнения: возражает, просит, конфликтует, играет сотрудника/клиента/коллегу.
6. Если роль нельзя уверенно определить по тексту, ставь "неизвестно" и confidence ниже 0.6.
7. Не превращай весь длинный монолог в одну огромную реплику: дели на смысловые фрагменты по 1-5 предложений.
8. Объединяй только подряд идущие фрагменты одной роли, если они действительно связаны.
9. Сохраняй таймкод начала фрагмента, если в строке есть формат [MM:SS].
10. В summary кратко напиши, сколько ролей удалось определить и где есть сомнения.
11. Верни JSON по схеме.
""".strip()
