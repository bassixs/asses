from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
import re
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


@dataclass(frozen=True)
class InputTranscriptLine:
    timestamp: str | None
    text: str
    source_speaker: str | None = None


class SpeakerRole(BaseModel):
    speaker: str
    role: RoleName


class SpeakerRoleMap(BaseModel):
    speakers: list[SpeakerRole] = Field(default_factory=list)


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

    speaker_role_map = await _map_source_speakers_to_roles(lines)
    if speaker_role_map:
        segments = [
            RoleSegment(
                role=speaker_role_map.get(line.source_speaker or "", "ведущий"),
                timestamp=line.timestamp,
                text=line.text,
            )
            for line in lines
        ]
        return _format_role_segments(_prepare_export_segments(segments))

    labeled_segments: list[RoleSegment] = []
    for chunk in _chunk_lines(lines):
        labeled_segments.extend(await _label_role_chunk(chunk))

    return _format_role_segments(_prepare_export_segments(labeled_segments))


async def _label_role_chunk(lines: list[InputTranscriptLine]) -> list[RoleSegment]:
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
                text=source.text,
            )
        )
    return segments


async def _map_source_speakers_to_roles(lines: list[InputTranscriptLine]) -> dict[str, RoleName]:
    speakers = sorted({line.source_speaker for line in lines if line.source_speaker})
    if len(speakers) < 2:
        return {}
    direct_roles = {speaker: speaker for speaker in speakers if speaker in {"ведущий", "участник"}}
    if set(direct_roles.values()) == {"ведущий", "участник"}:
        return direct_roles
    if len(speakers) > 2:
        speakers = _select_primary_speakers(lines, speakers)

    try:
        raw = await complete_json(
            system_prompt=_speaker_map_system_prompt(),
            user_prompt=_build_speaker_map_user_prompt(lines, speakers),
            json_schema=SpeakerRoleMap.model_json_schema(),
            temperature=0.0,
            max_tokens=1200,
        )
        mapping = SpeakerRoleMap.model_validate(raw)
    except (YandexGPTError, ValidationError) as exc:
        logger.warning("Failed to map source speakers, heuristic mapping will be used: %s", exc)
        return _heuristic_speaker_role_map(lines, speakers)

    role_by_speaker = {item.speaker: item.role for item in mapping.speakers if item.speaker in speakers}
    if set(role_by_speaker.values()) != {"ведущий", "участник"}:
        return _heuristic_speaker_role_map(lines, speakers)
    return role_by_speaker


def _parse_input_lines(transcript: str) -> list[InputTranscriptLine]:
    lines: list[InputTranscriptLine] = []
    for raw_line in transcript.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("[") and "]" in line:
            timestamp, text = line[1:].split("]", maxsplit=1)
            source_speaker, clean_text = _split_source_speaker(text.strip())
            lines.append(
                InputTranscriptLine(
                    timestamp=timestamp.strip(),
                    text=clean_text,
                    source_speaker=source_speaker,
                )
            )
        else:
            source_speaker, clean_text = _split_source_speaker(line)
            lines.append(InputTranscriptLine(timestamp=None, text=clean_text, source_speaker=source_speaker))
    return lines


def _split_source_speaker(text: str) -> tuple[str | None, str]:
    if ":" not in text:
        return None, text
    candidate, rest = text.split(":", maxsplit=1)
    candidate = candidate.strip()
    if not candidate or len(candidate) > 64:
        return None, text
    lowered = candidate.lower()
    if lowered in {"ведущий", "участник"} or lowered.startswith("speaker") or lowered.startswith("spk"):
        return candidate, rest.strip()
    if re.fullmatch(r"[a-zA-Z0-9_-]{1,32}", candidate):
        return candidate, rest.strip()
    return None, text


def _chunk_lines(lines: list[InputTranscriptLine], *, max_chars: int = 6500) -> list[list[InputTranscriptLine]]:
    chunks: list[list[InputTranscriptLine]] = []
    current: list[InputTranscriptLine] = []
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


def _build_role_chunk_user_prompt(lines: list[InputTranscriptLine]) -> str:
    formatted_lines = []
    for index, line in enumerate(lines, start=1):
        timestamp = f"[{line.timestamp}] " if line.timestamp else ""
        source_speaker = f"{line.source_speaker}: " if line.source_speaker else ""
        formatted_lines.append(f"{index}. {timestamp}{source_speaker}{line.text}")
    return "Разметь каждую строку:\n\n" + "\n".join(formatted_lines)


def _build_speaker_map_user_prompt(lines: list[InputTranscriptLine], speakers: list[str]) -> str:
    examples: list[str] = []
    for speaker in speakers:
        speaker_lines = _sample_speaker_lines(lines, speaker=speaker, max_lines=18)
        examples.append(f"Спикер {speaker}:")
        for line in speaker_lines:
            timestamp = f"[{line.timestamp}] " if line.timestamp else ""
            examples.append(f"- {timestamp}{line.text}")
    return (
        "Определи, какой технический speakerTag соответствует ведущему, а какой участнику.\n"
        f"Доступные speakerTag: {', '.join(speakers)}\n\n"
        + "\n".join(examples)
    )


def _select_primary_speakers(lines: list[InputTranscriptLine], speakers: list[str]) -> list[str]:
    stats: dict[str, tuple[int, int]] = {speaker: (0, 0) for speaker in speakers}
    for line in lines:
        if not line.source_speaker or line.source_speaker not in stats:
            continue
        count, chars = stats[line.source_speaker]
        stats[line.source_speaker] = (count + 1, chars + len(line.text))
    return sorted(speakers, key=lambda speaker: (stats[speaker][1], stats[speaker][0]), reverse=True)[:2]


def _sample_speaker_lines(
    lines: list[InputTranscriptLine],
    *,
    speaker: str,
    max_lines: int,
) -> list[InputTranscriptLine]:
    speaker_lines = [line for line in lines if line.source_speaker == speaker]
    if len(speaker_lines) <= max_lines:
        return speaker_lines

    window = max(1, max_lines // 3)
    middle_start = max(0, (len(speaker_lines) // 2) - (window // 2))
    sampled = (
        speaker_lines[:window]
        + speaker_lines[middle_start : middle_start + window]
        + speaker_lines[-window:]
    )

    result: list[InputTranscriptLine] = []
    seen: set[tuple[str | None, str]] = set()
    for line in sampled:
        key = (line.timestamp, line.text)
        if key in seen:
            continue
        seen.add(key)
        result.append(line)
    return result[:max_lines]


def _prepare_export_segments(segments: list[RoleSegment]) -> list[RoleSegment]:
    prepared = _smooth_role_segments(segments)
    if settings.transcript_export_merge_same_role:
        prepared = _merge_consecutive_role_segments(prepared)
    return prepared


def _format_role_segments(segments: list[RoleSegment]) -> str:
    return "\n\n".join(_format_role_segment(segment) for segment in segments if segment.text.strip()).strip()


def _format_role_segment(segment: RoleSegment) -> str:
    timestamp = f"[{segment.timestamp}] " if settings.transcript_export_include_timestamps and segment.timestamp else ""
    role = segment.role.capitalize()
    return f"{timestamp}{role}: {segment.text.strip()}"


def _merge_consecutive_role_segments(segments: list[RoleSegment]) -> list[RoleSegment]:
    merged: list[RoleSegment] = []
    for segment in segments:
        text = segment.text.strip()
        if not text:
            continue
        if merged and merged[-1].role == segment.role:
            previous = merged[-1]
            merged[-1] = RoleSegment(
                role=previous.role,
                timestamp=previous.timestamp,
                text=_join_segment_text(previous.text, text),
            )
            continue
        merged.append(RoleSegment(role=segment.role, timestamp=segment.timestamp, text=text))
    return merged


def _join_segment_text(previous: str, current: str) -> str:
    previous = previous.strip()
    current = current.strip()
    previous_normalized = _normalize_for_overlap(previous)
    current_normalized = _normalize_for_overlap(current)
    if not current_normalized:
        return previous
    if current_normalized in previous_normalized:
        return previous
    if previous_normalized and previous_normalized in current_normalized:
        return current
    return f"{previous} {current}".strip()


def _normalize_for_overlap(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^\w\s]+", " ", text, flags=re.UNICODE)
    return re.sub(r"\s+", " ", text).strip()


def _smooth_role_segments(segments: list[RoleSegment]) -> list[RoleSegment]:
    if len(segments) < 3:
        return segments

    smoothed = segments[:]
    for index in range(1, len(segments) - 1):
        previous = smoothed[index - 1]
        current = smoothed[index]
        next_segment = segments[index + 1]
        if previous.role != next_segment.role or current.role == previous.role:
            continue
        if _is_short_bridge_segment(current) or _looks_like_role_leak(current, previous.role):
            smoothed[index] = RoleSegment(role=previous.role, timestamp=current.timestamp, text=current.text)
    return smoothed


def _is_short_bridge_segment(segment: RoleSegment) -> bool:
    return len(segment.text.split()) <= 4


def _looks_like_role_leak(segment: RoleSegment, surrounding_role: RoleName) -> bool:
    text = segment.text.lower()
    if surrounding_role == "ведущий":
        return _looks_like_leading_text(text)
    return _looks_like_participant_text(text)


def _heuristic_speaker_role_map(lines: list[InputTranscriptLine], speakers: list[str]) -> dict[str, RoleName]:
    scores: dict[str, int] = {speaker: 0 for speaker in speakers}
    for line in lines:
        if not line.source_speaker or line.source_speaker not in scores:
            continue
        text = line.text.lower()
        if _looks_like_leading_text(text):
            scores[line.source_speaker] += 2
        if "?" in text:
            scores[line.source_speaker] += 1

    leading_speaker = max(scores, key=scores.get)
    return {
        speaker: ("ведущий" if speaker == leading_speaker else "участник")
        for speaker in speakers
    }


def _heuristic_role_segment(line: InputTranscriptLine) -> RoleSegment:
    text = line.text.lower()
    role: RoleName
    if _looks_like_leading_text(text):
        role = "ведущий"
    elif _looks_like_participant_text(text):
        role = "участник"
    else:
        role = "ведущий"
    return RoleSegment(role=role, timestamp=line.timestamp, text=line.text)


def _looks_like_leading_text(text: str) -> bool:
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
    return any(cue in text for cue in leading_cues)


def _looks_like_participant_text(text: str) -> bool:
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
    return any(cue in text for cue in participant_cues)


def _speaker_map_system_prompt() -> str:
    return """
Ты размечаешь транскрипт ассессмент-центра.

Есть ровно две роли:
1. "ведущий" — задает вопросы, объясняет упражнение, дает инструкции, управляет встречей.
2. "участник" — отвечает на вопросы, говорит о себе, своих задачах, трудностях, решениях.

Тебе даны технические speakerTag из системы распознавания и примеры реплик каждого speakerTag.
Нужно вернуть JSON: каждому speakerTag назначь одну роль.
Роли должны быть распределены так, чтобы один speakerTag был "ведущий", второй — "участник".
Не добавляй других ролей.
""".strip()


def _role_breakdown_system_prompt() -> str:
    return """
Ты — ассистент HR-ассессмента. Нужно разметить транскрипт интервью или упражнения по ролям.

Правила:
1. В этом упражнении всегда только две роли: "ведущий" и "участник".
2. Верни ровно столько segments, сколько строк получил пользователь.
3. Не объединяй строки, не пропускай строки, не добавляй новые строки.
4. Для каждой строки определи только role.
5. Не исправляй, не переписывай и не переформулируй text. Верни text как во входной строке.
6. Таймкод сохраняй из входной строки.
7. "ведущий" обычно приветствует, задает вопросы, объясняет упражнение, дает инструкции, уточняет, завершает этап.
8. "участник" обычно отвечает от первого лица, говорит о себе, своих задачах, решениях, трудностях, целях, мотивации.
9. Если строка похожа на вопрос, инструкцию или организационную реплику, выбирай "ведущий".
10. Если строка похожа на ответ оцениваемого участника, выбирай "участник".
11. Верни JSON по схеме.
""".strip()
