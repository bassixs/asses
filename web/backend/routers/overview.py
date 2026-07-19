from __future__ import annotations

from collections import defaultdict

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import (
    AssessmentCenter,
    Exercise,
    ExerciseTemplate,
    NotebookFillResult,
    Participant,
    ParticipantReport,
)
from bot.services.reports import normalize_competence_name
from web.backend.deps import get_session

router = APIRouter(tags=["overview"])

# ТЗ competency scale: 0..3 in 0.5 steps (see observer_notebook._level_from_percent).
LEVEL_MAX = 3.0

# Level bands for the distribution chart (ordered low → high).
_BANDS = [
    ("Не проявлена", 0.0, 0.0),
    ("Ниже нормы", 0.5, 1.0),
    ("Норма", 1.5, 2.0),
    ("Выше нормы", 2.5, 3.0),
]


def _band_for(level: float) -> str:
    for name, lo, hi in _BANDS:
        if lo <= level <= hi:
            return name
    return _BANDS[-1][0]


@router.get("/overview")
async def overview(session: AsyncSession = Depends(get_session)) -> dict:
    """Aggregate metrics for the analytics dashboard.

    Computes counts and, over every processed notebook, the average competency level
    per competence and the distribution of measurements across the ТЗ level bands.
    """
    centers = await session.scalar(select(func.count()).select_from(AssessmentCenter)) or 0
    participants = await session.scalar(select(func.count()).select_from(Participant)) or 0
    exercises = await session.scalar(select(func.count()).select_from(Exercise)) or 0
    processed = await session.scalar(select(func.count()).select_from(NotebookFillResult)) or 0
    reports = await session.scalar(select(func.count()).select_from(ParticipantReport)) or 0

    # Catalog readiness: how many exercises are actually selectable during assessment.
    catalog_total = await session.scalar(select(func.count()).select_from(ExerciseTemplate)) or 0
    catalog_rows = list(await session.scalars(select(ExerciseTemplate)))
    catalog_usable = sum(1 for t in catalog_rows if t.is_usable)
    catalog_no_notebook = sum(1 for t in catalog_rows if t.understood and not t.notebook_path)
    catalog_draft = catalog_total - catalog_usable - catalog_no_notebook

    fills = list(await session.scalars(select(NotebookFillResult)))
    exercise_center = dict((await session.execute(select(Exercise.id, Exercise.center_id))).all())
    center_names = dict((await session.execute(select(AssessmentCenter.id, AssessmentCenter.name))).all())
    center_participants = dict(
        (await session.execute(
            select(Participant.center_id, func.count()).group_by(Participant.center_id)
        )).all()
    )
    center_exercises = dict(
        (await session.execute(
            select(Exercise.center_id, func.count()).group_by(Exercise.center_id)
        )).all()
    )

    sums: dict[str, float] = defaultdict(float)
    counts: dict[str, int] = defaultdict(int)
    band_counts: dict[str, int] = {name: 0 for name, _, _ in _BANDS}
    measurements = 0
    level_total = 0.0
    center_sum: dict[int, float] = defaultdict(float)
    center_count: dict[int, int] = defaultdict(int)
    center_processed: dict[int, set[int]] = defaultdict(set)

    for fill in fills:
        center_id = exercise_center.get(fill.exercise_id)
        if center_id is not None and fill.exercise_id is not None:
            center_processed[center_id].add(fill.exercise_id)
        levels = (fill.result_json or {}).get("levels", {}) or {}
        for competence, data in levels.items():
            raw = data.get("level") if isinstance(data, dict) else data
            try:
                level = float(raw)
            except (TypeError, ValueError):
                continue
            name = normalize_competence_name(str(competence))
            sums[name] += level
            counts[name] += 1
            band_counts[_band_for(level)] += 1
            measurements += 1
            level_total += level
            if center_id is not None:
                center_sum[center_id] += level
                center_count[center_id] += 1

    by_center = sorted(
        (
            {
                "id": cid,
                "name": name,
                "participants": center_participants.get(cid, 0),
                "exercises": center_exercises.get(cid, 0),
                "processed": len(center_processed.get(cid, set())),
                "avg_level": (
                    round(center_sum[cid] / center_count[cid], 2) if center_count.get(cid) else None
                ),
            }
            for cid, name in center_names.items()
        ),
        key=lambda item: (item["processed"], item["exercises"]),
        reverse=True,
    )

    avg_by_competence = sorted(
        (
            {"name": name, "avg": round(sums[name] / counts[name], 2), "count": counts[name]}
            for name in sums
        ),
        key=lambda item: item["avg"],
        reverse=True,
    )

    return {
        "counts": {
            "centers": centers,
            "participants": participants,
            "exercises": exercises,
            "processed": processed,
            "reports": reports,
        },
        "level_max": LEVEL_MAX,
        "avg_level": round(level_total / measurements, 2) if measurements else 0,
        "measurements": measurements,
        "avg_by_competence": avg_by_competence,
        "level_bands": [
            {"name": name, "count": band_counts[name]} for name, _, _ in _BANDS
        ],
        "by_center": by_center,
        "catalog": {
            "total": catalog_total,
            "usable": catalog_usable,
            "needs_notebook": catalog_no_notebook,
            "draft": catalog_draft,
        },
    }
