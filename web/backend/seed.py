from __future__ import annotations

import logging
from datetime import datetime, timezone

from sqlalchemy import select

from bot.database import async_session_maker
from bot.models import ExerciseTemplate
from bot.models.exercise_template import STATUS_READY
from bot.services.exercise_context import load_exercise_library

logger = logging.getLogger(__name__)


def _instructions_from_entry(entry: dict) -> str:
    parts: list[str] = []
    if entry.get("participant_role"):
        parts.append(f"Роль оцениваемого участника: {entry['participant_role']}")
    if entry.get("role_play"):
        parts.append(f"Что происходит в записи: {entry['role_play']}")
    if entry.get("observable_notes"):
        parts.append(f"Какие проявления создаёт упражнение: {entry['observable_notes']}")
    competencies = entry.get("competencies") or []
    if competencies:
        parts.append("Компетенции упражнения: " + ", ".join(competencies))
    return "\n\n".join(parts)


def _understanding_from_entry(entry: dict) -> dict:
    """Understanding card for a built-in exercise, taken from the curated library.

    These four exercises are hand-curated and the whole pipeline has been tested on
    them, so they ship pre-verified. The blank notebook is still HR's to attach.
    """
    return {
        "summary": entry.get("role_play") or "",
        "format": "групповое" if "групп" in (entry.get("name") or "").lower() else "индивидуальное",
        "participant_role": entry.get("participant_role") or "",
        "facilitator_role": "",
        "expected_situations": [entry["observable_notes"]] if entry.get("observable_notes") else [],
        "competencies_covered": entry.get("competencies") or [],
        "not_observable": [],
        "nz_guidance": (
            "Ставь «НЗ», если упражнение не создало ситуации, в которой индикатор мог бы проявиться."
        ),
        "gaps": [],
        "understood": True,
        "understood_reason": (
            "Встроенное упражнение из библиотеки системы: сценарий, роли и компетенции "
            "заданы заранее и проверены на реальных записях."
        ),
        "source": "builtin",
    }


async def seed_builtin_templates() -> None:
    """Import the bundled exercise library into the catalog once, as ready entries.

    Idempotent: entries whose name already exists are skipped, so restarts and
    later edits by HR are never overwritten.
    """
    library = load_exercise_library()
    if not library:
        return

    now = datetime.now(timezone.utc)
    created = 0
    async with async_session_maker() as session:
        existing = set(await session.scalars(select(ExerciseTemplate.name)))
        for entry in library.values():
            name = (entry.get("name") or "").strip()
            if not name or name in existing:
                continue
            session.add(
                ExerciseTemplate(
                    name=name,
                    description="Встроенное упражнение из библиотеки системы. Приложите пустой блокнот наблюдателя, чтобы использовать его в оценке.",
                    status=STATUS_READY,
                    instructions_text=_instructions_from_entry(entry),
                    understanding_json=_understanding_from_entry(entry),
                    understood=True,
                    checked_at=now,
                    activated_at=now,
                )
            )
            created += 1
        if created:
            await session.commit()
            logger.info("Seeded %s built-in exercise templates", created)
