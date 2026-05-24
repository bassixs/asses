from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator

from bot.config import settings
from bot.services.yandex_gpt import complete_json

logger = logging.getLogger(__name__)


class CompetencyAssessment(BaseModel):
    name: str
    manifested: bool
    score: int = Field(ge=0, le=5)
    evidence: list[str] = Field(default_factory=list)
    comment: str


class AssessmentReport(BaseModel):
    competencies: list[CompetencyAssessment]
    overall_summary: str
    risks: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)

    @field_validator("competencies")
    @classmethod
    def competencies_must_not_be_empty(cls, value: list[CompetencyAssessment]) -> list[CompetencyAssessment]:
        if not value:
            raise ValueError("competencies must not be empty")
        return value


def build_system_prompt() -> str:
    competencies = "\n".join(f"- {name}" for name in settings.competencies)
    return f"""
Ты — эксперт по HR-ассесменту, оценке управленческих компетенций и интервью по компетенциям.
Твоя задача — строго и доказательно оценить кандидата или руководителя по транскрипту интервью.

Компетенции для оценки:
{competencies}

Правила оценки:
1. Используй только факты из транскрипта. Не додумывай биографию, мотивы или контекст.
2. Для каждой компетенции верни:
   - name: название компетенции из списка;
   - manifested: true, если в транскрипте есть поведенческие индикаторы компетенции;
   - score: целое число от 0 до 5;
   - evidence: список точных коротких цитат из транскрипта, подтверждающих оценку;
   - comment: короткое пояснение на русском языке.
3. Если данных недостаточно, ставь manifested=false, score=0 или 1 и объясняй нехватку данных.
4. Не используй общие похвалы. Каждая оценка должна быть связана с конкретной цитатой.
5. Цитаты в evidence должны быть дословными фрагментами транскрипта, без пересказа.
6. Не возвращай Markdown, XML или обычный текст. Только валидный JSON.

Формат ответа:
{{
  "competencies": [
    {{
      "name": "Название компетенции",
      "manifested": true,
      "score": 0,
      "evidence": ["точная цитата"],
      "comment": "краткое пояснение"
    }}
  ],
  "overall_summary": "краткий общий вывод",
  "risks": ["ключевой риск"],
  "recommendations": ["что уточнить на следующем этапе"]
}}
""".strip()


async def analyze_transcript(transcript: str) -> dict[str, Any]:
    """Analyze transcript with YandexGPT and return a validated dict."""
    system_prompt = build_system_prompt()
    user_prompt = f"Транскрипт интервью:\n\n{transcript}"
    raw_result = await complete_json(
        system_prompt=system_prompt,
        user_prompt=user_prompt,
        json_schema=AssessmentReport.model_json_schema(),
    )

    try:
        report = AssessmentReport.model_validate(raw_result)
    except ValidationError as exc:
        logger.error("Invalid assessment JSON schema: %s", exc)
        raise

    return report.model_dump()
