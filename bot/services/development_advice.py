from __future__ import annotations

import logging
from typing import Any

from bot.config import settings
from bot.services.llm_json import complete_json_openai_compatible
from bot.services.yandex_gpt import complete_json

logger = logging.getLogger(__name__)


_SYSTEM_PROMPT = """
Ты — эксперт по оценке и развитию персонала (ассессмент-центр).
Тебе дают название компетенции, её уровень и поведенческие индикаторы, которые являются зонами роста участника.
Сформируй практичные рекомендации развития на русском языке.

Требования:
- Не копируй формулировки индикаторов дословно. Переформулируй их в понятные действия и развивающие шаги.
- Пиши конкретно: что именно делать, какое поведение тренировать, как закреплять.
- Без общих фраз и воды. Ориентируйся на управленческий контекст.

Верни ТОЛЬКО JSON-объект с двумя полями:
- "recommendations": массив из 3-5 строк — краткие рекомендации для отчёта (что развивать и зачем).
- "ipr_actions": массив из 4-6 строк — конкретные шаги для плана развития по модели 70/20/10
  (70% практика на рабочем месте; 20% обратная связь и наставничество; 10% обучение, курсы, литература).
Пример формата: {"recommendations": ["..."], "ipr_actions": ["..."]}
"""

_JSON_SCHEMA = {
    "type": "object",
    "properties": {
        "recommendations": {"type": "array", "items": {"type": "string"}},
        "ipr_actions": {"type": "array", "items": {"type": "string"}},
    },
}


async def enrich_competencies_with_advice(
    competencies: dict[str, Any],
    *,
    participant_name: str,
) -> None:
    """Add LLM-generated 'recommendations' and 'ipr_actions' to each competence in place."""
    for competence, data in competencies.items():
        if not isinstance(data, dict):
            continue
        growth_zones = data.get("growth_zones", []) or []
        if not growth_zones:
            data["recommendations"] = []
            data["ipr_actions"] = []
            continue

        try:
            advice = await _generate_competency_advice(
                competence=competence,
                level=data.get("avg_level", 0),
                strengths=data.get("strengths", []) or [],
                growth_zones=growth_zones,
                participant_name=participant_name,
            )
        except Exception as exc:  # noqa: BLE001 - advice must never break report generation
            logger.error("Advice generation failed for competence %s: %s", competence, exc)
            advice = {"recommendations": [], "ipr_actions": []}

        data["recommendations"] = advice["recommendations"] or _fallback_actions(growth_zones)
        data["ipr_actions"] = advice["ipr_actions"] or _fallback_actions(growth_zones)


async def _generate_competency_advice(
    *,
    competence: str,
    level: Any,
    strengths: list[str],
    growth_zones: list[str],
    participant_name: str,
) -> dict[str, list[str]]:
    growth_text = "\n".join(f"- {item}" for item in growth_zones)
    strengths_text = "\n".join(f"- {item}" for item in strengths[:8]) or "—"
    user_prompt = (
        f"Участник: {participant_name}\n"
        f"Компетенция: {competence}\n"
        f"Средний уровень (шкала 0-3): {level}\n\n"
        f"Сильные стороны:\n{strengths_text}\n\n"
        f"Зоны роста (индикаторы, требующие развития):\n{growth_text}\n\n"
        "Сформируй recommendations и ipr_actions строго по инструкции. Верни только JSON."
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


def _coerce_advice(raw: Any) -> dict[str, list[str]]:
    recommendations: list[str] = []
    ipr_actions: list[str] = []
    if isinstance(raw, dict):
        recommendations = _as_str_list(raw.get("recommendations") or raw.get("recommendation"))
        ipr_actions = _as_str_list(raw.get("ipr_actions") or raw.get("actions") or raw.get("development_actions"))
    elif isinstance(raw, list):
        recommendations = _as_str_list(raw)
    return {"recommendations": recommendations, "ipr_actions": ipr_actions}


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
