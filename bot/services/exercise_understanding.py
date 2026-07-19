from __future__ import annotations

import logging
from collections import defaultdict
from typing import Any

from bot.config import settings
from bot.services.llm_json import complete_json_openai_compatible
from bot.services.observer_notebook import IndicatorRow

logger = logging.getLogger(__name__)

# Send every indicator. Sampling them was a false economy: a typical notebook is ~90
# rows (~2.5k tokens), which is nothing next to the materials, while a truncated list
# makes the model report "не все индикаторы приведены" as a gap — and that gap blocks
# activation forever. The cap only guards against an absurdly large notebook.
MAX_INDICATORS_TOTAL = 400
MAX_MATERIALS_CHARS = 14000

_SYSTEM_PROMPT = (
    "Ты — методолог ассессмент-центра. Тебе дают материалы упражнения (инструкции ведущего, "
    "наблюдателя, участника) и список компетенций/индикаторов из блокнота наблюдателя, по которому "
    "это упражнение будут оценивать.\n\n"
    "Твоя задача — понять упражнение НАСТОЛЬКО, чтобы потом корректно оценивать по нему запись: "
    "кто в записи ролевой игрок (ведущий), кто оцениваемый участник, какие ситуации упражнение "
    "создаёт специально, и какие индикаторы в нём в принципе НЕ могут проявиться (их надо будет "
    "помечать «НЗ», а не «−»).\n\n"
    "Будь честен. Если материалов не хватает, чтобы уверенно вести оценку, — так и скажи и "
    "перечисли, чего именно не хватает. Не выдумывай сценарий, которого нет в материалах.\n\n"
    "Верни ТОЛЬКО JSON со схемой:\n"
    "{\n"
    '  "summary": "2-4 предложения: что это за упражнение и как оно проходит",\n'
    '  "format": "индивидуальное | групповое | иное — коротко",\n'
    '  "participant_role": "кого играет оцениваемый участник",\n'
    '  "facilitator_role": "кого играет ведущий/ролевой игрок; если его нет — так и напиши",\n'
    '  "expected_situations": ["ситуации, которые упражнение создаёт специально"],\n'
    '  "competencies_covered": ["компетенции из блокнота, которые реально замеряются"],\n'
    '  "not_observable": ["индикаторы/компетенции из блокнота, которые в этом упражнении проявиться не могут"],\n'
    '  "nz_guidance": "как решать про НЗ именно в этом упражнении",\n'
    '  "gaps": ["чего не хватает в материалах; пустой список, если всё есть"],\n'
    '  "understood": true/false,\n'
    '  "understood_reason": "почему понимаешь/не понимаешь упражнение"\n'
    "}\n"
    "understood = true только если материалов достаточно, чтобы вести оценку без догадок."
)


def _indicator_digest(indicators: list[IndicatorRow]) -> str:
    """Competence → full indicator listing for the prompt."""
    grouped: dict[str, list[str]] = defaultdict(list)
    for item in indicators[:MAX_INDICATORS_TOTAL]:
        grouped[item.competence].append(item.indicator)

    lines: list[str] = []
    for competence, texts in grouped.items():
        shown = [t for t in texts if t]
        lines.append(f"— {competence or 'без названия'} (индикаторов: {len(shown)})")
        lines.extend(f"    · {text}" for text in shown)

    if len(indicators) > MAX_INDICATORS_TOTAL:
        lines.append(f"(показаны первые {MAX_INDICATORS_TOTAL} из {len(indicators)} индикаторов)")
    return "\n".join(lines)


async def analyze_exercise_understanding(
    *,
    name: str,
    description: str | None,
    instructions_text: str | None,
    indicators: list[IndicatorRow],
) -> dict[str, Any]:
    """Ask the LLM to study an exercise's materials and report its understanding.

    Returns the understanding card as a dict (see _SYSTEM_PROMPT schema), always with
    a boolean "understood" and a list "gaps".
    """
    materials = (instructions_text or "").strip()
    if len(materials) > MAX_MATERIALS_CHARS:
        materials = materials[:MAX_MATERIALS_CHARS].rstrip()

    parts = [f"Упражнение: «{name}»"]
    if description:
        parts.append(f"Пояснение от HR: {description}")
    parts.append(
        "\nМатериалы упражнения:\n" + (materials if materials else "(материалы не приложены)")
    )
    if indicators:
        parts.append(
            "\nБлокнот наблюдателя — компетенции и индикаторы, по которым будут оценивать:\n"
            + _indicator_digest(indicators)
        )
    else:
        parts.append("\nБлокнот наблюдателя не приложен — список индикаторов неизвестен.")
    parts.append("\nРазбери упражнение и верни только JSON.")

    raw = await complete_json_openai_compatible(
        provider=settings.analysis_llm_provider,
        model=settings.analysis_llm_model,
        system_prompt=_SYSTEM_PROMPT,
        user_prompt="\n".join(parts),
        temperature=0.2,
        max_tokens=settings.analysis_llm_max_tokens,
        timeout_seconds=settings.analysis_llm_timeout_seconds,
        json_mode=settings.analysis_llm_json_mode,
    )
    return _coerce(raw, has_materials=bool(materials), has_indicators=bool(indicators))


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    if isinstance(value, str) and value.strip():
        return [value.strip()]
    return []


def _coerce(raw: Any, *, has_materials: bool, has_indicators: bool) -> dict[str, Any]:
    data = raw if isinstance(raw, dict) else {}

    gaps = _as_str_list(data.get("gaps"))
    understood = bool(data.get("understood"))

    # Hard guards: without materials or a notebook there is nothing to understand,
    # regardless of what the model claims.
    if not has_materials:
        understood = False
        gaps.insert(0, "Не приложены материалы упражнения (инструкции/методичка).")
    if not has_indicators:
        understood = False
        gaps.insert(0, "Не приложен пустой блокнот наблюдателя — неизвестно, что оценивать.")

    return {
        "summary": str(data.get("summary") or "").strip(),
        "format": str(data.get("format") or "").strip(),
        "participant_role": str(data.get("participant_role") or "").strip(),
        "facilitator_role": str(data.get("facilitator_role") or "").strip(),
        "expected_situations": _as_str_list(data.get("expected_situations")),
        "competencies_covered": _as_str_list(data.get("competencies_covered")),
        "not_observable": _as_str_list(data.get("not_observable")),
        "nz_guidance": str(data.get("nz_guidance") or "").strip(),
        "gaps": gaps,
        "understood": understood,
        "understood_reason": str(data.get("understood_reason") or "").strip(),
    }
