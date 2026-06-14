from __future__ import annotations

import asyncio
import logging
from typing import Any

from bot.config import settings
from bot.services.competency_content import get_competency_content
from bot.services.llm_json import complete_json_openai_compatible
from bot.services.yandex_gpt import complete_json

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """
Ты — эксперт по оценке и развитию персонала (ассессмент-центр).
Тебе дают компетенцию, её уровень, проявленные индикаторы (сильные стороны) и
непроявленные индикаторы (зоны роста) участника.

Сделай и верни ТОЛЬКО JSON-объект:
1. "report_strengths": перепиши сильные стороны в «отчётном» стиле — короткие обобщённые
   позитивные формулировки от третьего лица (5-9 пунктов). Объединяй близкие по смыслу, убирай дубли.
2. "report_growth_zones": перепиши зоны роста в мягком «отчётном» стиле от третьего лица
   («может упускать из внимания…», «может не всегда…») — 3-7 пунктов.
3. "recommendations": 3-5 кратких персональных рекомендаций для отчёта по зонам роста.
4. "ipr": объект индивидуального плана развития по этой компетенции:
   - "goal": цель развития (1-2 предложения, что развить и зачем);
   - "workplace": действие категории «Развитие на рабочем месте» (применение в ежедневных задачах);
   - "projects": действие категории «Специальные задачи и проекты»;
   - "feedback": действие категории «Поиск обратной связи» (что и у кого запрашивать);
   - "mentoring": действие категории «Наставничество»;
   - "expected_results": ожидаемые результаты (как поймём, что развитие удалось).

Требования: не копируй формулировки дословно — переформулируй; без воды; русский язык;
управленческий контекст. Если зон роста нет — recommendations верни пустым, в ipr заполни только goal.
Пример формата: {"report_strengths": ["..."], "report_growth_zones": ["..."], "recommendations": ["..."], "ipr": {"goal": "...", "workplace": "...", "projects": "...", "feedback": "...", "mentoring": "...", "expected_results": "..."}}
"""

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "report_strengths": {"type": "array", "items": {"type": "string"}},
        "report_growth_zones": {"type": "array", "items": {"type": "string"}},
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "ipr": {"type": "object"},
    },
}

_IPR_KEYS = ("goal", "workplace", "projects", "feedback", "mentoring", "expected_results")


async def enrich_competencies_with_advice(
    competencies: dict[str, Any],
    *,
    participant_name: str,
) -> None:
    """Add LLM-generated report-style text, recommendations and IPR plan to each competence."""
    semaphore = asyncio.Semaphore(max(1, settings.analysis_llm_max_concurrency))

    async def enrich_one(competence: str, data: dict[str, Any]) -> None:
        # Curated library content (literature/courses/practice tasks) for every competence.
        content = get_competency_content(competence)
        if content:
            data["literature"] = content.get("literature", []) or []
            data["courses"] = content.get("courses", []) or []
            data["practice_tasks"] = content.get("practice_tasks", []) or []

        strengths = data.get("strengths", []) or []
        growth_zones = data.get("growth_zones", []) or []
        if not strengths and not growth_zones:
            data["recommendations"] = []
            data["ipr"] = {}
            return

        async with semaphore:
            try:
                advice = await _generate_competency_advice(
                    competence=competence,
                    level=data.get("avg_level", 0),
                    strengths=strengths,
                    growth_zones=growth_zones,
                    participant_name=participant_name,
                )
            except Exception as exc:  # noqa: BLE001 - advice must never break report generation
                logger.error("Advice generation failed for competence %s: %s", competence, exc)
                advice = {"report_strengths": [], "report_growth_zones": [], "recommendations": [], "ipr": {}}

        # Report-style rewrites fall back to the raw (already cleaned) lists.
        if advice["report_strengths"]:
            data["report_strengths"] = advice["report_strengths"]
        if advice["report_growth_zones"]:
            data["report_growth_zones"] = advice["report_growth_zones"]
        data["recommendations"] = advice["recommendations"] or (_fallback_actions(growth_zones) if growth_zones else [])
        data["ipr"] = advice["ipr"]

    await asyncio.gather(
        *(enrich_one(competence, data) for competence, data in competencies.items() if isinstance(data, dict))
    )


async def _generate_competency_advice(
    *,
    competence: str,
    level: Any,
    strengths: list[str],
    growth_zones: list[str],
    participant_name: str,
) -> dict[str, list[str]]:
    growth_text = "\n".join(f"- {item}" for item in growth_zones) or "—"
    strengths_text = "\n".join(f"- {item}" for item in strengths) or "—"
    user_prompt = (
        f"Участник: {participant_name}\n"
        f"Компетенция: {competence}\n"
        f"Средний уровень (шкала 0-3): {level}\n\n"
        f"Проявленные индикаторы (сильные стороны):\n{strengths_text}\n\n"
        f"Непроявленные индикаторы (зоны роста):\n{growth_text}\n\n"
        "Сформируй report_strengths, report_growth_zones, recommendations и ipr строго по инструкции. "
        "Верни только JSON."
    )

    if settings.analysis_llm_provider.lower().strip() == "yandex":
        raw = await complete_json(
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            json_schema=_JSON_SCHEMA,
            temperature=0.3,
            max_tokens=settings.analysis_llm_max_tokens,
        )
    else:
        raw = await complete_json_openai_compatible(
            provider=settings.analysis_llm_provider,
            model=settings.analysis_llm_model,
            system_prompt=_SYSTEM_PROMPT,
            user_prompt=user_prompt,
            temperature=0.3,
            max_tokens=settings.analysis_llm_max_tokens,
            timeout_seconds=settings.analysis_llm_timeout_seconds,
            json_mode=settings.analysis_llm_json_mode,
        )

    return _coerce_advice(raw)


def _coerce_advice(raw: Any) -> dict[str, Any]:
    report_strengths: list[str] = []
    report_growth_zones: list[str] = []
    recommendations: list[str] = []
    ipr: dict[str, str] = {}
    if isinstance(raw, dict):
        report_strengths = _as_str_list(raw.get("report_strengths") or raw.get("strengths"))
        report_growth_zones = _as_str_list(raw.get("report_growth_zones") or raw.get("growth_zones"))
        recommendations = _as_str_list(raw.get("recommendations") or raw.get("recommendation"))
        ipr = _coerce_ipr(raw.get("ipr"))
    elif isinstance(raw, list):
        recommendations = _as_str_list(raw)
    return {
        "report_strengths": report_strengths,
        "report_growth_zones": report_growth_zones,
        "recommendations": recommendations,
        "ipr": ipr,
    }


def _coerce_ipr(value: Any) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for key in _IPR_KEYS:
        raw = value.get(key)
        if isinstance(raw, str) and raw.strip():
            out[key] = raw.strip()
        elif isinstance(raw, list):
            joined = " ".join(str(item).strip() for item in raw if str(item).strip())
            if joined:
                out[key] = joined
    return out


def _as_str_list(value: Any) -> list[str]:
    if isinstance(value, str):
        text = value.strip()
        return [text] if text else []
    if not isinstance(value, list):
        return []
    out: list[str] = []
    for entry in value:
        if isinstance(entry, str) and entry.strip():
            out.append(entry.strip())
        elif isinstance(entry, dict):
            text = entry.get("text") or entry.get("action") or entry.get("recommendation") or entry.get("step")
            if isinstance(text, str) and text.strip():
                out.append(text.strip())
    return out


def _fallback_actions(growth_zones: list[str]) -> list[str]:
    return [
        f"Отработать поведение: {item}. Подготовить 1-2 рабочих ситуации и заранее определить критерии успешного действия."
        for item in growth_zones[:6]
    ]
