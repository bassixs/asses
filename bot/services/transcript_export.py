from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field, ValidationError

from bot.config import settings
from bot.services.speechkit import normalize_transcript_text
from bot.services.yandex_gpt import YandexGPTError, complete_json

logger = logging.getLogger(__name__)

RoleName = Literal["ведущий", "участник"]


class RoleSegment(BaseModel):
    role: RoleName
    timestamp: str | None = None
    text: str


class RoleLabeledChunk(BaseModel):
    segments: list[RoleSegment] = Field(default_factory=list)


async def build_transcript_text_file(*, transcript: str, record_id: int) -> Path:
    reports_dir = settings.download_dir.parent / "reports"
    reports_dir.mkdir(parents=True, exist_ok=True)
    output_path = reports_dir / f"transcript_record_{record_id}.txt"

    cleaned_transcript = normalize_transcript_text(transcript)
    role_text = await _build_role_labeled_transcript(cleaned_transcript)
    content = "\n\n".join(
        [
            f"Расшифровка записи #{record_id}",
            role_text,
        ]
    )
    output_path.write_text(content, encoding="utf-8")
    return output_path


async def _build_role_labeled_transcript(transcript: str) -> str:
    lines = _parse_input_lines(transcript)
    if not lines:
        return ""

    labeled_segments: list[RoleSegment] = []
    for chunk in _chunk_lines(lines):
        labeled_segments.extend(await _label_role_chunk(chunk))

    return "\n".join(_format_role_segment(segment) for segment in labeled_segments).strip()


async def _label_role_chunk(lines: list[RoleSegment]) -> list[RoleSegment]:
    try:
        raw = await complete_json(
            system_prompt=_role_breakdown_system_prompt(),
            user_prompt=_build_role_chunk_user_prompt(lines),
            json_schema=RoleLabeledChunk.model_json_schema(),
            temperature=0.05,
            max_tokens=8000,
        )
        labeled = RoleLabeledChunk.model_validate(raw)
    except (YandexGPTError, ValidationError) as exc:
        logger.warning("Failed to label transcript chunk, heuristic roles will be used: %s", exc)
        return [_heuristic_role_segment(line) for line in lines]

    if len(labeled.segments) != len(lines):
        logger.warning(
            "Role labeling returned unexpected segment count: expected=%s actual=%s",
            len(lines),
            len(labeled.segments),
        )
        return [_heuristic_role_segment(line) for line in lines]

    segments: list[RoleSegment] = []
    for source, segment in zip(lines, labeled.segments, strict=True):
        segments.append(
            RoleSegment(
                role=segment.role,
                timestamp=source.timestamp,
                text=segment.text.strip() or source.text,
            )
        )
    return segments


def _parse_input_lines(transcript: str) -> list[RoleSegment]:
    lines: list[RoleSegment] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and "]" in line:
            timestamp, text = line[1:].split("]", maxsplit=1)
            lines.append(RoleSegment(role="ведущий", timestamp=timestamp.strip(), text=text.strip()))
        else:
            lines.append(RoleSegment(role="ведущий", timestamp=None, text=line))
    return lines


def _chunk_lines(lines: list[RoleSegment], *, max_chars: int = 6500) -> list[list[RoleSegment]]:
    chunks: list[list[RoleSegment]] = []
    current: list[RoleSegment] = []
    current_chars = 0
    for line in lines:
        line_chars = len(line.text) + len(line.timestamp or "") + 16
        if current and current_chars + line_chars > max_chars:
            chunks.append(current)
            current = []
            current_chars = 0
        current.append(line)
        current_chars += line_chars
    if current:
        chunks.append(current)
    return chunks


def _build_role_chunk_user_prompt(lines: list[RoleSegment]) -> str:
    formatted_lines = []
    for index, line in enumerate(lines, start=1):
        timestamp = f"[{line.timestamp}] " if line.timestamp else ""
        formatted_lines.append(f"{index}. {timestamp}{line.text}")
    return "Разметь каждую строку:\n\n" + "\n".join(formatted_lines)


def _format_role_segment(segment: RoleSegment) -> str:
    timestamp = f"[{segment.timestamp}] " if segment.timestamp else ""
    return f"{timestamp}{segment.role}: {segment.text.strip()}"


def _heuristic_role_segment(line: RoleSegment) -> RoleSegment:
    text = line.text.lower()
    leading_cues = (
        "скажите",
        "давайте",
        "пожалуйста",
        "какую цель",
        "как вы",
        "что хотели",
        "упражнение завершено",
        "ознакомьтесь",
        "мой вопрос",
    )
    participant_cues = (
        "я ",
        "мне ",
        "у меня",
        "если честно",
        "не успела",
        "не знаю",
        "хотелось бы",
        "могу сказать",
    )
    if any(cue in text for cue in leading_cues):
        role: RoleName = "ведущий"
    elif any(cue in text for cue in participant_cues):
        role = "участник"
    else:
        role = "ведущий"
    return RoleSegment(role=role, timestamp=line.timestamp, text=line.text)


def _role_breakdown_system_prompt() -> str:
    return """
Ты — ассистент HR-ассессмента. Нужно разметить транскрипт интервью или упражнения по ролям.

Правила:
1. В этом упражнении всегда только две роли: "ведущий" и "участник".
2. Верни ровно столько segments, сколько строк получил пользователь.
3. Не объединяй строки, не пропускай строки, не добавляй новые строки.
4. Для каждой строки определи role и аккуратно приведи text в читаемый вид.
5. Можно исправлять очевидные ошибки распознавания, пунктуацию, лишние повторы слов и падежи, но нельзя менять смысл или добавлять новые факты.
6. Таймкод сохраняй из входной строки.
7. "ведущий" обычно приветствует, задает вопросы, объясняет упражнение, дает инструкции, уточняет, завершает этап.
8. "участник" обычно отвечает от первого лица, говорит о себе, своих задачах, решениях, трудностях, целях, мотивации.
9. Если строка похожа на вопрос, инструкцию или организационную реплику, выбирай "ведущий".
10. Если строка похожа на ответ оцениваемого участника, выбирай "участник".
11. Верни JSON по схеме.
""".strip()
