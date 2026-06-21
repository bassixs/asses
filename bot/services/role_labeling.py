from __future__ import annotations

import asyncio
import json
import logging
import re
import socket
from typing import Any, Literal

import aiohttp
from pydantic import BaseModel, Field, ValidationError

from bot.config import settings
from bot.services.exercise_context import build_role_labeling_hint
from bot.services.speechkit import normalize_transcript_text

logger = logging.getLogger(__name__)

RoleName = Literal["ведущий", "участник"]


class RoleLabelingError(RuntimeError):
    pass


class RoleSegment(BaseModel):
    role: RoleName
    text: str = Field(min_length=1)


class RoleLabeledTranscript(BaseModel):
    segments: list[RoleSegment] = Field(default_factory=list)


async def label_transcript_roles(
    transcript: str,
    *,
    assessed_participant_name: str | None = None,
    exercise_name: str | None = None,
) -> str:
    cleaned = _strip_export_header(normalize_transcript_text(transcript))
    if not settings.role_labeling_enabled or not cleaned:
        return cleaned

    if _looks_role_labeled(cleaned) and not assessed_participant_name:
        return _normalize_role_labeled_text(cleaned)

    chunks = _chunk_transcript(cleaned, max_chars=settings.role_labeling_chunk_chars)
    labeled_parts: list[str] = []
    previous_tail = ""

    for index, chunk in enumerate(chunks, start=1):
        logger.info("Role labeling transcript chunk %s/%s chars=%s", index, len(chunks), len(chunk))
        chunk_result = await _label_chunk(
            chunk=chunk,
            previous_tail=previous_tail,
            assessed_participant_name=assessed_participant_name,
            exercise_name=exercise_name,
        )
        labeled_parts.append(_format_segments(chunk_result.segments))
        previous_tail = _tail_text(chunk_result.segments)

    return _merge_labeled_parts(labeled_parts)


def extract_participant_transcript(transcript: str) -> str:
    """Return only assessed participant lines from an already role-labeled transcript.

    If the transcript is not role-labeled, return the normalized text unchanged so
    legacy records and failed role-labeling results can still be analyzed.
    """
    cleaned = _strip_export_header(normalize_transcript_text(transcript))
    if not _looks_role_labeled(cleaned):
        return cleaned

    segments = _parse_role_labeled_lines(cleaned)
    participant_segments = [segment for segment in segments if segment.role == "участник"]
    if not participant_segments:
        return cleaned
    return _format_segments(participant_segments)


async def _label_chunk(
    *,
    chunk: str,
    previous_tail: str,
    assessed_participant_name: str | None,
    exercise_name: str | None,
    depth: int = 0,
) -> RoleLabeledTranscript:
    try:
        return await _label_chunk_once(
            chunk=chunk,
            previous_tail=previous_tail,
            assessed_participant_name=assessed_participant_name,
            exercise_name=exercise_name,
        )
    except RoleLabelingError:
        if depth >= 3 or len(chunk) <= 1200:
            raise
        logger.warning("Role labeling chunk failed, splitting and retrying: depth=%s chars=%s", depth, len(chunk))

    parts = _split_long_text(chunk, max_chars=max(1000, len(chunk) // 2))
    if len(parts) < 2:
        raise RoleLabelingError("Role labeling failed and chunk could not be split further")

    segments: list[RoleSegment] = []
    tail = previous_tail
    for part in parts:
        labeled = await _label_chunk(
            chunk=part,
            previous_tail=tail,
            assessed_participant_name=assessed_participant_name,
            exercise_name=exercise_name,
            depth=depth + 1,
        )
        segments.extend(labeled.segments)
        tail = _tail_text(labeled.segments)
    return RoleLabeledTranscript(segments=segments)


async def _label_chunk_once(
    *,
    chunk: str,
    previous_tail: str,
    assessed_participant_name: str | None,
    exercise_name: str | None,
) -> RoleLabeledTranscript:
    payload = await _complete_json(
        system_prompt=_system_prompt(
            assessed_participant_name=assessed_participant_name,
            exercise_name=exercise_name,
        ),
        user_prompt=_user_prompt(
            chunk=chunk,
            previous_tail=previous_tail,
            assessed_participant_name=assessed_participant_name,
            exercise_name=exercise_name,
        ),
    )
    try:
        labeled = RoleLabeledTranscript.model_validate(payload)
    except ValidationError as exc:
        raise RoleLabelingError(f"Role labeling returned invalid JSON shape: {payload}") from exc

    if not labeled.segments:
        raise RoleLabelingError(f"Role labeling returned no segments: {payload}")

    return _sanitize_labeled_transcript(labeled)


async def _complete_json(*, system_prompt: str, user_prompt: str) -> dict[str, Any]:
    provider = settings.role_labeling_provider.lower().strip()
    if provider == "neuroapi":
        base_url = settings.neuroapi_base_url
        api_key = settings.neuroapi_api_key
        force_ipv4 = settings.neuroapi_force_ipv4
    elif provider == "aitunnel":
        base_url = settings.aitunnel_base_url
        api_key = settings.aitunnel_api_key
        force_ipv4 = settings.aitunnel_force_ipv4
    else:
        raise RoleLabelingError(f"Unsupported role labeling provider: {settings.role_labeling_provider}")

    if not api_key:
        raise RoleLabelingError(f"Role labeling API key is not configured for provider: {provider}")

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    body = {
        "model": settings.role_labeling_model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "temperature": settings.role_labeling_temperature,
        "max_tokens": settings.role_labeling_max_tokens,
    }
    if settings.role_labeling_json_mode:
        body["response_format"] = {"type": "json_object"}
    timeout = aiohttp.ClientTimeout(total=settings.role_labeling_timeout_seconds)
    connector = aiohttp.TCPConnector(family=socket.AF_INET if force_ipv4 else socket.AF_UNSPEC)

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers, connector=connector) as session:
            async with session.post(f"{base_url.rstrip('/')}/chat/completions", json=body) as response:
                payload = await _read_response(response)
                if response.status >= 400:
                    raise RoleLabelingError(f"Role labeling returned HTTP {response.status}: {payload}")
    except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
        raise RoleLabelingError(f"Role labeling network error: {exc}") from exc

    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RoleLabelingError(f"Unexpected role labeling response: {payload}") from exc

    if not isinstance(content, str):
        raise RoleLabelingError(f"Role labeling response content is not text: {payload}")

    try:
        parsed = json.loads(_extract_json_object(content))
    except json.JSONDecodeError as exc:
        raise RoleLabelingError(f"Role labeling returned non-JSON content: {content[:1000]}") from exc

    if not isinstance(parsed, dict):
        raise RoleLabelingError(f"Role labeling returned non-object JSON: {parsed}")
    return parsed


async def _read_response(response: aiohttp.ClientResponse) -> dict[str, Any]:
    try:
        payload = await response.json(content_type=None)
    except (aiohttp.ContentTypeError, ValueError):
        return {"text": await response.text()}
    if isinstance(payload, dict):
        return payload
    return {"payload": payload}


def _sanitize_labeled_transcript(labeled: RoleLabeledTranscript) -> RoleLabeledTranscript:
    segments: list[RoleSegment] = []
    for segment in labeled.segments:
        text = _clean_segment_text(segment.text)
        if not text:
            continue
        role = segment.role.lower()
        if role not in {"ведущий", "участник"}:
            continue
        segments.append(RoleSegment(role=role, text=text))  # type: ignore[arg-type]
    return RoleLabeledTranscript(segments=segments)


def _extract_json_object(content: str) -> str:
    text = content.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return text
    return text[start : end + 1]


def _chunk_transcript(transcript: str, *, max_chars: int) -> list[str]:
    paragraphs = [part.strip() for part in re.split(r"\n{2,}", transcript) if part.strip()]
    if not paragraphs:
        paragraphs = _split_long_text(transcript, max_chars=max_chars)

    chunks: list[str] = []
    current: list[str] = []
    current_chars = 0
    for paragraph in paragraphs:
        if len(paragraph) > max_chars:
            if current:
                chunks.append("\n\n".join(current))
                current = []
                current_chars = 0
            chunks.extend(_split_long_text(paragraph, max_chars=max_chars))
            continue

        separator_chars = 2 if current else 0
        if current and current_chars + separator_chars + len(paragraph) > max_chars:
            chunks.append("\n\n".join(current))
            current = []
            current_chars = 0
        current.append(paragraph)
        current_chars += separator_chars + len(paragraph)

    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _split_long_text(text: str, *, max_chars: int) -> list[str]:
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        if len(sentence) > max_chars:
            if current:
                chunks.append(current.strip())
                current = ""
            chunks.extend(sentence[index : index + max_chars] for index in range(0, len(sentence), max_chars))
            continue
        if current and len(current) + 1 + len(sentence) > max_chars:
            chunks.append(current.strip())
            current = ""
        current = f"{current} {sentence}".strip()
    if current:
        chunks.append(current.strip())
    return chunks


def _format_segments(segments: list[RoleSegment]) -> str:
    lines: list[str] = []
    for segment in segments:
        role = "Ведущий" if segment.role == "ведущий" else "Участник"
        lines.append(f"{role}: {segment.text.strip()}")
    return "\n\n".join(lines)


def _merge_labeled_parts(parts: list[str]) -> str:
    segments = _parse_role_labeled_lines("\n\n".join(part for part in parts if part.strip()))
    if not settings.transcript_export_merge_same_role:
        return _format_segments(segments)

    merged: list[RoleSegment] = []
    for segment in segments:
        if merged and merged[-1].role == segment.role:
            merged[-1] = RoleSegment(
                role=merged[-1].role,
                text=f"{merged[-1].text.strip()} {segment.text.strip()}",
            )
        else:
            merged.append(segment)
    return _format_segments(merged)


def _parse_role_labeled_lines(text: str) -> list[RoleSegment]:
    segments: list[RoleSegment] = []
    pattern = re.compile(r"(?im)^\s*(ведущий|участник)\s*:\s*")
    matches = list(pattern.finditer(text))
    for index, match in enumerate(matches):
        role = match.group(1).lower()
        start = match.end()
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment_text = _clean_segment_text(text[start:end])
        if segment_text:
            segments.append(RoleSegment(role=role, text=segment_text))  # type: ignore[arg-type]
    return segments


def _normalize_role_labeled_text(text: str) -> str:
    return _format_segments(_parse_role_labeled_lines(text))


def _looks_role_labeled(text: str) -> bool:
    return bool(re.search(r"(?im)^\s*(ведущий|участник)\s*:", text))


def _clean_segment_text(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^(ведущий|участник)\s*:\s*", "", text, flags=re.IGNORECASE).strip()
    return text


def _strip_export_header(text: str) -> str:
    return re.sub(r"^\s*Расшифровка записи #\d+\s*", "", text, flags=re.IGNORECASE).strip()


def _tail_text(segments: list[RoleSegment], *, max_chars: int = 1200) -> str:
    tail = _format_segments(segments[-6:])
    return tail[-max_chars:]


def _system_prompt(*, assessed_participant_name: str | None, exercise_name: str | None) -> str:
    known_context = ""
    if assessed_participant_name or exercise_name:
        exercise_hint = build_role_labeling_hint(exercise_name)
        known_context = "\n".join(
            part
            for part in (
                f"Известный оцениваемый участник: {assessed_participant_name}." if assessed_participant_name else "",
                f"Название упражнения: {exercise_name}." if exercise_name else "",
                exercise_hint,
            )
            if part
        )
        known_context = f"\n\nКонтекст из системы:\n{known_context}\n"

    return f"""
Ты размечаешь расшифровку упражнения ассессмент-центра по ролям.
{known_context}

Роли всегда только две:
- "ведущий": ассессор, наблюдатель, интервьюер, ролевой игрок, сотрудник в упражнении, любой человек кроме оцениваемого участника.
- "участник": оцениваемый кандидат/руководитель, который проходит упражнение и демонстрирует компетенции.

Главное правило:
Ты размечаешь роли НЕ по тому, кто больше говорит, НЕ по первому лицу и НЕ по имени персонажа, а по статусу в ассессменте.
"участник" — только оцениваемый человек, чьи компетенции нужно оценить.
"ведущий" — все остальные голоса: ведущий, наблюдатель, интервьюер, ролевой игрок, подчинённый/сотрудник в ролевой встрече, клиент, ассистент, ассессор.

Как определить оцениваемого, если имя прямо не передано:
1. Проверь весь фрагмент и предыдущий контекст, кто демонстрирует управленческое поведение: ставит задачу, принимает решения, ведёт трудный разговор, даёт обратную связь, договаривается о сроках, управляет сопротивлением.
2. В ролевых упражнениях оцениваемый часто играет руководителя/менеджера. Ролевой сотрудник может много говорить о своих проблемах, усталости, отпуске и возражениях, но он НЕ становится "участником", если его поведение не оценивается.
3. Если один говорящий жалуется, сопротивляется, отвечает как сотрудник или клиент, а второй пытается провести управленческий разговор, то оцениваемый обычно второй.
4. Если в системном контексте указано имя оцениваемого, все реплики этого человека помечай "участник", даже если он задаёт вопросы или ведёт разговор. Реплики других людей помечай "ведущий".
5. Если в тексте встречается обращение к имени, не путай адресата и говорящего. Фраза "Марина, скажите..." означает, что говорящий не Марина.
6. Если имена похожи или распознавание ошиблось, опирайся на устойчивый паттерн диалога и цель упражнения, а не на единичную фразу.
7. Если уверенность низкая, выбери вариант, который лучше сохраняет для "участника" оцениваемое управленческое поведение, а не эмоциональные ответы ролевого сотрудника.
8. Если вход уже содержит метки "ведущий"/"участник", не доверяй им автоматически: проверь их заново по правилам выше и исправь, если они противоречат статусу оцениваемого.

ВАЖНО про сегментацию (это критично):
Распознавание речи НЕ разделяет говорящих, поэтому одна входная строка часто склеивает реплики
РАЗНЫХ людей в один длинный кусок. Твоя задача — РАЗРЕЗАТЬ такие склейки. Признаки смены говорящего:
- приветствия и ответы ("Здравствуйте, вызывали?" — сотрудник; "Да, добрый день, Марина" — руководитель);
- вопрос одного и ответ другого ("Что нужно сделать?" / "Нужно подготовить...");
- служебные фразы ведущего/ассессора ("Марина ушла", "Маргарита, задам вам вопросы", "упражнение завершено");
- резкая смена позиции (управленческая постановка задачи ↔ жалобы/сопротивление сотрудника);
- переход к разбору: после слов вроде "Марина ушла"/"задам вам вопросы" идёт интервью ассессора —
  это чередование: ВОПРОС ассессора ("ведущий") → ОТВЕТ оцениваемого ("участник"), и так по очереди.

Жёсткое правило длины: НЕ оставляй длинных склеенных монологов. Если в одном куске больше 2-4 предложений
И при этом меняется говорящий, роль или явно идёт «вопрос-ответ» — обязательно раздели на несколько реплик.
Особенно внимательно к длинным блокам: в них почти всегда смешаны двое-трое говорящих — разрежь их полностью.
Лучше много коротких точных реплик, чем один большой кусок с чужими словами внутри (иначе реплики
оцениваемого участника потеряются и оценка будет неверной).

Держи роли СОГЛАСОВАННЫМИ на протяжении всего текста: один и тот же человек НЕ может быть то
"участник", то "ведущий". Оцениваемый участник — всегда "участник", во всех частях упражнения.

КАК ТОЧНО найти оцениваемого участника (самый надёжный признак):
В конце упражнения идёт РАЗБОР — ассессор задаёт вопросы ("какую цель ставили?", "довольны ли
результатом?", "что бы изменили?"), а ОДИН человек отвечает про СВОИ действия и цели в упражнении.
Этот отвечающий — и есть оцениваемый участник. Запомни его и в РОЛЕВОЙ ИГРЕ (начало упражнения)
помечай ВСЕ его реплики как "участник" — даже если там он ставит задачу, а ДРУГОЙ человек (ролевой
сотрудник) жалуется на загрузку/усталость/отпуск и говорит от первого лица. Жалующийся сотрудник —
это "ведущий" (ролевой игрок), а руководитель, который даёт задание и потом отвечает ассессору, —
"участник". Не дай обмануть себя тем, что сотрудник говорит много и эмоционально.

Задача:
1. Раздели входной текст на последовательные реплики диалога (разрезая склейки разных говорящих).
2. Каждой реплике назначь role: "ведущий" или "участник".
3. Верни только JSON-объект вида {{"segments":[{{"role":"ведущий","text":"..."}},{{"role":"участник","text":"..."}}]}}.
4. Не добавляй краткое содержание, комментарии, выводы, заголовки и markdown.
5. Не переписывай смысл и не украшай текст. Можно только аккуратно разделить длинный текст на реплики и убрать явные повторы/мусор распознавания.
6. Не выдумывай факты и фразы, которых нет во входном тексте.
7. Не добавляй тайминги, если их нет во входе.
8. Не добавляй отдельную роль для ролевого игрока. Ролевой игрок всегда "ведущий".
""".strip()


def _user_prompt(
    *,
    chunk: str,
    previous_tail: str,
    assessed_participant_name: str | None,
    exercise_name: str | None,
) -> str:
    context = f"Предыдущий фрагмент для контекста:\n{previous_tail}\n\n" if previous_tail else ""
    system_context = ""
    if assessed_participant_name or exercise_name:
        system_context = "\n".join(
            part
            for part in (
                f"Оцениваемый участник: {assessed_participant_name}" if assessed_participant_name else "",
                f"Упражнение: {exercise_name}" if exercise_name else "",
            )
            if part
        )
        system_context = f"{system_context}\n\n"
    return (
        f"{context}"
        f"{system_context}"
        "Разметь следующий фрагмент. Верни только JSON по схеме segments.\n\n"
        f"Фрагмент:\n{chunk}"
    )
