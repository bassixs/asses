from __future__ import annotations

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import (
    AssessmentCenter,
    AssessmentResult,
    DevelopmentPlan,
    Exercise,
    InterviewRecord,
    MediaProcessingJob,
    NotebookFillResult,
    ObserverNotebook,
    Participant,
    ParticipantReport,
)

# Deletion is done with explicit statements in dependency order rather than relying on
# ORM cascades or ON DELETE clauses: SQLite does not enforce foreign keys by default,
# so a cascade would silently leave orphaned rows behind.


async def _paths(session: AsyncSession, column, where) -> list[str]:
    return [str(v) for v in await session.scalars(select(column).where(where)) if v]


async def delete_exercises(session: AsyncSession, exercise_ids: list[int]) -> dict:
    """Remove exercises and everything recorded against them."""
    if not exercise_ids:
        return {"exercises": 0, "results": 0, "files": []}

    record_ids = list(
        await session.scalars(
            select(InterviewRecord.id).where(InterviewRecord.exercise_id.in_(exercise_ids))
        )
    )
    processed = len(
        list(
            await session.scalars(
                select(NotebookFillResult.id).where(
                    NotebookFillResult.exercise_id.in_(exercise_ids)
                )
            )
        )
    )

    # Candidate files to remove from disk once the rows are gone. Actual deletion happens
    # later and only if nothing else still points at the file (an exercise's notebook may
    # be the shared catalog-template file — a reference check protects it).
    files = (
        await _paths(session, InterviewRecord.file_path, InterviewRecord.exercise_id.in_(exercise_ids))
        + await _paths(session, ObserverNotebook.file_path, ObserverNotebook.exercise_id.in_(exercise_ids))
        + await _paths(session, NotebookFillResult.output_path, NotebookFillResult.exercise_id.in_(exercise_ids))
    )

    if record_ids:
        await session.execute(
            delete(AssessmentResult).where(AssessmentResult.record_id.in_(record_ids))
        )
    await session.execute(
        delete(NotebookFillResult).where(NotebookFillResult.exercise_id.in_(exercise_ids))
    )
    await session.execute(
        delete(MediaProcessingJob).where(MediaProcessingJob.exercise_id.in_(exercise_ids))
    )
    await session.execute(
        delete(ObserverNotebook).where(ObserverNotebook.exercise_id.in_(exercise_ids))
    )
    await session.execute(
        delete(InterviewRecord).where(InterviewRecord.exercise_id.in_(exercise_ids))
    )
    await session.execute(delete(Exercise).where(Exercise.id.in_(exercise_ids)))
    return {"exercises": len(exercise_ids), "results": processed, "files": files}


async def delete_participants(session: AsyncSession, participant_ids: list[int]) -> dict:
    """Remove participants, their exercises, reports and development plans."""
    if not participant_ids:
        return {"participants": 0, "exercises": 0, "results": 0, "files": []}

    exercise_ids = list(
        await session.scalars(
            select(Exercise.id).where(Exercise.participant_id.in_(participant_ids))
        )
    )
    stats = await delete_exercises(session, exercise_ids)

    files = stats["files"] + (
        await _paths(session, ParticipantReport.output_path, ParticipantReport.participant_id.in_(participant_ids))
        + await _paths(session, DevelopmentPlan.output_path, DevelopmentPlan.participant_id.in_(participant_ids))
    )

    await session.execute(
        delete(ParticipantReport).where(ParticipantReport.participant_id.in_(participant_ids))
    )
    await session.execute(
        delete(DevelopmentPlan).where(DevelopmentPlan.participant_id.in_(participant_ids))
    )
    await session.execute(delete(Participant).where(Participant.id.in_(participant_ids)))
    return {"participants": len(participant_ids), **stats, "files": files}


async def delete_center(session: AsyncSession, center_id: int) -> dict:
    """Remove a whole assessment centre with every participant and result inside it."""
    participant_ids = list(
        await session.scalars(select(Participant.id).where(Participant.center_id == center_id))
    )
    stats = await delete_participants(session, participant_ids)

    # Exercises attached straight to the centre (no participant) would otherwise linger.
    stray = list(await session.scalars(select(Exercise.id).where(Exercise.center_id == center_id)))
    if stray:
        extra = await delete_exercises(session, stray)
        stats["exercises"] += extra["exercises"]
        stats["results"] += extra["results"]
        stats["files"] = stats["files"] + extra["files"]

    await session.execute(delete(AssessmentCenter).where(AssessmentCenter.id == center_id))
    return stats
