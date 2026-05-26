from __future__ import annotations

from collections import defaultdict
from pathlib import Path
from typing import Any


def build_participant_report_text(
    *,
    participant_name: str,
    exercise_results: list[dict[str, Any]],
) -> tuple[str, dict[str, Any]]:
    summary = _aggregate(exercise_results)
    lines = [
        f"Индивидуальный отчет участника ассессмент-центра",
        f"Участник: {participant_name}",
        "",
        "Краткий вывод",
        "Отчет сформирован автоматически на основе заполненных блокнотов наблюдателя.",
        "",
    ]

    for competence, data in summary.items():
        lines.append(f"Компетенция: {competence}")
        lines.append(f"Средний уровень: {data['avg_level']}")
        lines.append("Сильные стороны:")
        lines.extend(_bullet_lines(data["strengths"]))
        lines.append("Зоны роста:")
        lines.extend(_bullet_lines(data["growth_zones"]))
        lines.append("Рекомендации:")
        lines.extend(_bullet_lines(_recommendations(data["growth_zones"])))
        lines.append("")

    return "\n".join(lines).strip(), {"competencies": summary}


def build_development_plan_text(
    *,
    participant_name: str,
    report_json: dict[str, Any],
) -> tuple[str, dict[str, Any]]:
    competencies = report_json.get("competencies", {})
    lines = [
        "Индивидуальный план развития",
        f"Участник: {participant_name}",
        "",
        "Цель ИПР",
        "Сфокусироваться на индикаторах, которые не проявились в упражнениях ассессмент-центра.",
        "",
    ]

    plan: dict[str, Any] = {}
    for competence, data in competencies.items():
        growth_zones = data.get("growth_zones", [])
        if not growth_zones:
            continue
        recommendations = _recommendations(growth_zones)
        plan[competence] = {"growth_zones": growth_zones, "recommendations": recommendations}
        lines.append(f"Компетенция: {competence}")
        lines.append("Зоны развития:")
        lines.extend(_bullet_lines(growth_zones))
        lines.append("Действия на 4-6 недель:")
        lines.extend(_bullet_lines(recommendations))
        lines.append("Как проверить прогресс:")
        lines.append("- Повторить упражнение или рабочий кейс и собрать поведенческие примеры.")
        lines.append("")

    if not plan:
        lines.append("Явных зон роста по обработанным упражнениям не найдено.")

    return "\n".join(lines).strip(), {"plan": plan}


def save_text_report(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _aggregate(exercise_results: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    by_competence: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"levels": [], "indicator_statuses": defaultdict(list), "indicator_quotes": defaultdict(list)}
    )

    for result in exercise_results:
        levels = result.get("levels", {})
        for competence, level_data in levels.items():
            if isinstance(level_data, dict):
                by_competence[competence]["levels"].append(float(level_data.get("level") or 0))

        indicators = {
            item.get("indicator_id"): item
            for item in result.get("indicators", [])
            if isinstance(item, dict)
        }
        for item in result.get("results", []):
            if not isinstance(item, dict):
                continue
            indicator = indicators.get(item.get("indicator_id"), {})
            competence = str(indicator.get("competence") or "Компетенция не указана")
            indicator_text = str(indicator.get("indicator") or item.get("indicator_id"))
            status = item.get("status")
            if status == "НЗ":
                continue
            by_competence[competence]["indicator_statuses"][indicator_text].append(status)
            for evidence in item.get("evidence", []) or []:
                if isinstance(evidence, dict) and evidence.get("quote"):
                    by_competence[competence]["indicator_quotes"][indicator_text].append(str(evidence["quote"]))

    output: dict[str, dict[str, Any]] = {}
    for competence, data in by_competence.items():
        strengths: list[str] = []
        growth_zones: list[str] = []
        for indicator_text, statuses in data["indicator_statuses"].items():
            if statuses and all(status == "+" for status in statuses):
                strengths.append(indicator_text)
            elif any(status == "-" for status in statuses):
                growth_zones.append(indicator_text)

        levels = data["levels"]
        avg_level = round(sum(levels) / len(levels), 2) if levels else 0
        output[competence] = {
            "avg_level": avg_level,
            "strengths": strengths,
            "growth_zones": growth_zones,
        }
    return output


def _recommendations(growth_zones: list[str]) -> list[str]:
    if not growth_zones:
        return ["Продолжать закреплять проявленные поведенческие индикаторы на рабочих задачах."]
    return [
        f"Отработать поведение: {item}. Подготовить 1-2 рабочих ситуации и заранее определить критерии успешного действия."
        for item in growth_zones[:6]
    ]


def _bullet_lines(items: list[str]) -> list[str]:
    if not items:
        return ["- Не выявлено по обработанным упражнениям."]
    return [f"- {item}" for item in items]
