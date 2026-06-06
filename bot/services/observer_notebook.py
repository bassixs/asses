from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Literal

from openpyxl import load_workbook
from openpyxl.styles import Alignment
from pydantic import BaseModel, Field, ValidationError, field_validator

from bot.config import settings
from bot.services.llm_json import LLMJSONError, complete_json_openai_compatible
from bot.services.role_labeling import extract_participant_transcript
from bot.services.yandex_gpt import complete_json

logger = logging.getLogger(__name__)

IndicatorStatus = Literal["+", "-", "НЗ"]


class NotebookProcessingError(RuntimeError):
    pass


@dataclass(frozen=True)
class IndicatorRow:
    indicator_id: str
    row: int
    competence: str
    indicator: str
    status_col: int = 4
    comment_col: int = 5
    level_col: int = 6


class IndicatorEvidence(BaseModel):
    timestamp: str | None = None
    quote: str


class IndicatorAnalysis(BaseModel):
    indicator_id: str
    status: IndicatorStatus
    evidence: list[IndicatorEvidence] = Field(default_factory=list)
    comment: str = ""
    observable_reason: str = ""


class NotebookAnalysisReport(BaseModel):
    role_summary: str = ""
    participant_summary: str = ""
    results: list[IndicatorAnalysis]

    @field_validator("results")
    @classmethod
    def results_must_not_be_empty(cls, value: list[IndicatorAnalysis]) -> list[IndicatorAnalysis]:
        if not value:
            raise ValueError("results must not be empty")
        return value


def extract_notebook_indicators(workbook_path: Path) -> list[IndicatorRow]:
    workbook = load_workbook(workbook_path)
    sheet = workbook.active
    indicators: list[IndicatorRow] = []
    current_competence = ""
    layout = _detect_notebook_layout(sheet)

    for row in range(1, sheet.max_row + 1):
        competence_raw = _cell_text(sheet.cell(row=row, column=layout["competence_col"]).value)
        indicator = _cell_text(sheet.cell(row=row, column=layout["indicator_col"]).value)
        status_header = _cell_text(sheet.cell(row=row, column=layout["status_col"]).value)

        if competence_raw and not _looks_like_column_header(competence_raw) and not _looks_like_level(competence_raw):
            current_competence = competence_raw

        if not indicator or _looks_like_column_header(indicator) or _looks_like_column_header(status_header):
            continue

        competence = "" if _looks_like_level(competence_raw) else competence_raw
        competence = competence or current_competence
        if not competence:
            competence = "Компетенция не указана"

        indicators.append(
            IndicatorRow(
                indicator_id=f"I{len(indicators) + 1:03d}",
                row=row,
                competence=competence,
                indicator=indicator,
                status_col=layout["status_col"],
                comment_col=layout["comment_col"],
                level_col=layout["level_col"],
            )
        )

    if not indicators:
        raise NotebookProcessingError(
            "В блокноте не найдены поведенческие индикаторы. "
            "Проверьте, что рядом с ними есть колонки 'Проявления' и 'Комментарии'."
        )

    return indicators


async def analyze_notebook_indicators(
    *,
    transcript: str,
    indicators: list[IndicatorRow],
) -> NotebookAnalysisReport:
    system_prompt = _build_notebook_system_prompt()
    participant_transcript = extract_participant_transcript(transcript)

    batch_size = max(1, settings.notebook_analysis_batch_size)
    batches = [indicators[i : i + batch_size] for i in range(0, len(indicators), batch_size)]

    all_results: list[IndicatorAnalysis] = []
    role_summary = ""
    participant_summary = ""
    succeeded = 0
    last_error: Exception | None = None

    for batch_index, batch in enumerate(batches, start=1):
        try:
            report = await _analyze_indicator_batch(
                system_prompt=system_prompt,
                transcript=participant_transcript,
                indicators=batch,
                batch_index=batch_index,
                batch_count=len(batches),
            )
        except (LLMJSONError, NotebookProcessingError) as exc:
            # One bad batch should not fail the whole exercise; its indicators are
            # marked "НЗ" later by _ensure_all_indicators.
            logger.error("Notebook analysis batch %s/%s failed: %s", batch_index, len(batches), exc)
            last_error = exc
            continue

        succeeded += 1
        all_results.extend(report.results)
        if not role_summary and report.role_summary:
            role_summary = report.role_summary
        if not participant_summary and report.participant_summary:
            participant_summary = report.participant_summary

    if succeeded == 0:
        raise NotebookProcessingError(
            f"Не удалось получить оценку блокнота ни по одному батчу ({len(batches)} шт.). "
            f"Последняя ошибка: {last_error}",
        )

    merged = NotebookAnalysisReport(
        role_summary=role_summary,
        participant_summary=participant_summary,
        results=all_results,
    )
    return _ensure_all_indicators(merged, indicators)


async def _analyze_indicator_batch(
    *,
    system_prompt: str,
    transcript: str,
    indicators: list[IndicatorRow],
    batch_index: int,
    batch_count: int,
) -> NotebookAnalysisReport:
    payload = [
        {
            "indicator_id": item.indicator_id,
            "competence": item.competence,
            "indicator": item.indicator,
        }
        for item in indicators
    ]
    user_prompt = _build_notebook_user_prompt(transcript=transcript, indicators=payload)
    logger.info("Notebook analysis batch %s/%s: indicators=%s", batch_index, batch_count, len(indicators))

    if settings.analysis_llm_provider.lower().strip() == "yandex":
        raw = await complete_json(
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            json_schema=NotebookAnalysisReport.model_json_schema(),
            temperature=0.05,
            max_tokens=settings.analysis_llm_max_tokens,
        )
    else:
        raw = await complete_json_openai_compatible(
            provider=settings.analysis_llm_provider,
            model=settings.analysis_llm_model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=settings.analysis_llm_temperature,
            max_tokens=settings.analysis_llm_max_tokens,
            timeout_seconds=settings.analysis_llm_timeout_seconds,
            json_mode=settings.analysis_llm_json_mode,
        )

    try:
        return NotebookAnalysisReport.model_validate(raw)
    except ValidationError as exc:
        logger.error("Invalid notebook analysis JSON (batch %s/%s): %s", batch_index, batch_count, exc)
        raise NotebookProcessingError(
            f"Модель вернула некорректную структуру оценки блокнота (батч {batch_index}/{batch_count}).",
        ) from exc


def fill_observer_notebook(
    *,
    input_path: Path,
    output_path: Path,
    indicators: list[IndicatorRow],
    report: NotebookAnalysisReport,
) -> dict[str, object]:
    workbook = load_workbook(input_path)
    sheet = workbook.active
    result_by_id = {item.indicator_id: item for item in report.results}
    indicator_by_row = {item.row: item for item in indicators}

    for indicator in indicators:
        result = result_by_id[indicator.indicator_id]
        sheet.cell(row=indicator.row, column=indicator.status_col).value = result.status
        sheet.cell(row=indicator.row, column=indicator.comment_col).value = _format_comment(result)
        sheet.cell(row=indicator.row, column=indicator.comment_col).alignment = Alignment(wrap_text=True, vertical="top")

    levels = _calculate_competency_levels(indicators, result_by_id)
    _write_competency_levels(sheet, indicator_by_row, levels)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    workbook.save(output_path)

    return {
        "role_summary": report.role_summary,
        "participant_summary": report.participant_summary,
        "indicator_count": len(indicators),
        "levels": levels,
        "indicators": [
            {
                "indicator_id": item.indicator_id,
                "competence": item.competence,
                "indicator": item.indicator,
                "row": item.row,
            }
            for item in indicators
        ],
        "results": [item.model_dump() for item in report.results],
    }


def _build_notebook_system_prompt() -> str:
    return """
Ты — эксперт ассессмент-центра и обученный наблюдатель.
Твоя задача — заполнить блокнот наблюдателя по транскрипту упражнения.

Правила:
1. Оценивай только реплики оцениваемого участника ассессмент-центра.
2. Не используй реплики наблюдателя, ведущего или ролевого игрока как evidence проявления.
3. Во входном транскрипте уже должен быть оставлен оцениваемый участник. Если всё же встретятся роли, используй только строки "Участник:".
4. Для каждого индикатора верни один статус:
   "+" — есть хотя бы одна релевантная цитата участника;
   "-" — индикатор мог наблюдаться в упражнении, но проявления участника нет;
   "НЗ" — индикатор объективно не мог наблюдаться в этом упражнении.
5. Каждый "+" должен иметь точную цитату. Если в транскрипте есть таймкод, верни его.
6. Для "-" evidence должен быть пустым.
7. Для "НЗ" evidence должен быть пустым, а observable_reason должен объяснять, почему ситуация не позволяла замерить индикатор.
8. Не придумывай цитаты, таймкоды, действия и роли.
9. Возвращай только валидный JSON по схеме.
""".strip()


def _build_notebook_user_prompt(*, transcript: str, indicators: list[dict[str, str]]) -> str:
    return f"""
Транскрипт упражнения:
{transcript}

Поведенческие индикаторы из блокнота наблюдателя:
{indicators}
""".strip()


def _ensure_all_indicators(
    report: NotebookAnalysisReport,
    indicators: list[IndicatorRow],
) -> NotebookAnalysisReport:
    expected = {item.indicator_id for item in indicators}
    existing = {item.indicator_id for item in report.results}
    missing = expected - existing
    if not missing:
        return report

    patched = list(report.results)
    for indicator_id in sorted(missing):
        patched.append(
            IndicatorAnalysis(
                indicator_id=indicator_id,
                status="НЗ",
                evidence=[],
                comment="Индикатор не был возвращен моделью.",
                observable_reason="Автоматически помечено как незамер из-за неполного ответа модели.",
            )
        )
    return NotebookAnalysisReport(
        role_summary=report.role_summary,
        participant_summary=report.participant_summary,
        results=patched,
    )


def _calculate_competency_levels(
    indicators: list[IndicatorRow],
    result_by_id: dict[str, IndicatorAnalysis],
) -> dict[str, dict[str, float | int]]:
    grouped: dict[str, list[IndicatorStatus]] = defaultdict(list)
    for indicator in indicators:
        grouped[indicator.competence].append(result_by_id[indicator.indicator_id].status)

    levels: dict[str, dict[str, float | int]] = {}
    for competence, statuses in grouped.items():
        observed = [status for status in statuses if status != "НЗ"]
        plus_count = sum(1 for status in observed if status == "+")
        observed_count = len(observed)
        percent = (plus_count / observed_count * 100) if observed_count else 0.0
        levels[competence] = {
            "plus_count": plus_count,
            "observed_count": observed_count,
            "percent": round(percent, 2),
            "level": _level_from_percent(percent) if observed_count else 0,
        }
    return levels


def _write_competency_levels(
    sheet,
    indicator_by_row: dict[int, IndicatorRow],
    levels: dict[str, dict[str, float | int]],
) -> None:
    written: set[str] = set()
    for row in range(1, sheet.max_row + 1):
        for column in (1, 2):
            competence = _cell_text(sheet.cell(row=row, column=column).value)
            if competence in levels and competence not in written:
                level_col = _level_column_for_competence(indicator_by_row, competence)
                sheet.cell(row=row, column=level_col).value = levels[competence]["level"]
                written.add(competence)

    for row in range(1, sheet.max_row + 1):
        indicator = indicator_by_row.get(row)
        if indicator and indicator.competence not in written:
            sheet.cell(row=row, column=indicator.level_col).value = levels[indicator.competence]["level"]
            written.add(indicator.competence)


def _level_from_percent(percent: float) -> float:
    if percent >= 90:
        return 3
    if percent >= 80:
        return 2.5
    if percent >= 60:
        return 2
    if percent >= 40:
        return 1.5
    if percent >= 20:
        return 1
    if percent >= 5:
        return 0.5
    return 0


def _format_comment(result: IndicatorAnalysis) -> str:
    if result.status != "+":
        return "" if result.status == "-" else result.observable_reason or result.comment

    evidence_lines = []
    for item in result.evidence:
        prefix = f"[{item.timestamp}] " if item.timestamp else ""
        evidence_lines.append(f"{prefix}«{item.quote}»")
    if result.comment:
        evidence_lines.append(result.comment)
    return "\n".join(evidence_lines)


def _cell_text(value: object) -> str:
    return str(value).strip() if value is not None else ""


def _detect_notebook_layout(sheet) -> dict[str, int]:
    for row in range(1, sheet.max_row + 1):
        headers = {
            column: _cell_text(sheet.cell(row=row, column=column).value)
            for column in range(1, sheet.max_column + 1)
        }
        status_col = next((column for column, text in headers.items() if text.casefold() == "проявления"), None)
        comment_col = next(
            (column for column, text in headers.items() if text.casefold() in {"комментарии", "комментарий"}),
            None,
        )
        if status_col and comment_col and status_col > 1:
            indicator_col = status_col - 1
            return {
                "competence_col": max(1, indicator_col - 1),
                "indicator_col": indicator_col,
                "status_col": status_col,
                "comment_col": comment_col,
                "level_col": comment_col + 1,
            }

    return {
        "competence_col": 2,
        "indicator_col": 3,
        "status_col": 4,
        "comment_col": 5,
        "level_col": 6,
    }


def _looks_like_level(text: str) -> bool:
    try:
        float(text.replace(",", "."))
    except ValueError:
        return False
    return True


def _level_column_for_competence(indicator_by_row: dict[int, IndicatorRow], competence: str) -> int:
    for indicator in indicator_by_row.values():
        if indicator.competence == competence:
            return indicator.level_col
    return 6


def _looks_like_column_header(text: str) -> bool:
    lowered = text.casefold()
    return lowered in {
        "компетенция",
        "компетенции",
        "поведенческие индикаторы",
        "индикаторы",
        "проявления",
        "комментарии",
        "комментарий",
    }
