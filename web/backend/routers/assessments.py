from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import (
    AssessmentCenter,
    Exercise,
    ExerciseTemplate,
    NotebookFillResult,
    ObserverNotebook,
    Participant,
    ParticipantReport,
    WebUser,
)
from bot.services.exercise_understanding import render_understanding_brief
from web.backend.deps import WEB_OWNER_ID, CurrentUser, current_user, get_session
from web.backend.purge import delete_center, delete_exercises, delete_participants
from web.backend.storage import delete_files_now_unreferenced
from web.backend.schemas import (
    CenterCreate,
    CenterOut,
    ExerciseCreate,
    ExerciseOut,
    ParticipantCreate,
    ParticipantOut,
)

router = APIRouter(tags=["assessments"])


def _participant_out(
    participant: Participant, *, has_report: bool = False, processed: int = 0
) -> ParticipantOut:
    return ParticipantOut(
        id=participant.id,
        code=participant.full_name,
        center_id=participant.center_id,
        has_report=has_report,
        processed_count=processed,
    )


async def _participant_state(participant_id: int, session: AsyncSession) -> tuple[bool, int]:
    """Whether a report was built, and how many exercises are already assessed."""
    report_id = await session.scalar(
        select(ParticipantReport.id).where(ParticipantReport.participant_id == participant_id).limit(1)
    )
    processed = await session.scalar(
        select(func.count(func.distinct(NotebookFillResult.exercise_id)))
        .join(Exercise, NotebookFillResult.exercise_id == Exercise.id)
        .where(Exercise.participant_id == participant_id)
    )
    return report_id is not None, processed or 0


def _exercise_out(
    exercise: Exercise, indicator_count: int | None = None, *, has_result: bool = False
) -> ExerciseOut:
    return ExerciseOut(
        id=exercise.id,
        name=exercise.name,
        participant_id=exercise.participant_id,
        center_id=exercise.center_id,
        has_instructions=bool(exercise.instructions_text),
        template_id=exercise.template_id,
        notebook_indicator_count=indicator_count,
        has_result=has_result,
    )


# ---- centers -------------------------------------------------------------------------------

@router.post("/centers", response_model=CenterOut)
async def create_center(
    payload: CenterCreate,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(current_user),
) -> CenterOut:
    center = AssessmentCenter(chat_id=WEB_OWNER_ID, user_id=user.id, name=payload.name.strip())
    session.add(center)
    await session.commit()
    await session.refresh(center)
    return CenterOut(
        id=center.id, name=center.name, created_at=center.created_at, created_by=user.username
    )


@router.get("/centers", response_model=list[CenterOut])
async def list_centers(session: AsyncSession = Depends(get_session)) -> list[CenterOut]:
    rows = list(await session.scalars(select(AssessmentCenter).order_by(AssessmentCenter.id.desc())))

    creators = dict(
        (await session.execute(select(WebUser.id, WebUser.username))).all()
    )
    participants = dict(
        (await session.execute(
            select(Participant.center_id, func.count()).group_by(Participant.center_id)
        )).all()
    )
    exercises = dict(
        (await session.execute(
            select(Exercise.center_id, func.count()).group_by(Exercise.center_id)
        )).all()
    )
    # Exercises that already have a filled notebook (one row per processed exercise).
    processed = dict(
        (await session.execute(
            select(Exercise.center_id, func.count(func.distinct(NotebookFillResult.exercise_id)))
            .join(NotebookFillResult, NotebookFillResult.exercise_id == Exercise.id)
            .group_by(Exercise.center_id)
        )).all()
    )

    return [
        CenterOut(
            id=c.id,
            name=c.name,
            created_at=c.created_at,
            participants=participants.get(c.id, 0),
            exercises=exercises.get(c.id, 0),
            processed=processed.get(c.id, 0),
            created_by=creators.get(c.user_id),
        )
        for c in rows
    ]


@router.get("/centers/{center_id}", response_model=CenterOut)
async def get_center(center_id: int, session: AsyncSession = Depends(get_session)) -> CenterOut:
    center = await session.get(AssessmentCenter, center_id)
    if center is None:
        raise HTTPException(status_code=404, detail="Центр не найден")
    return CenterOut(id=center.id, name=center.name, created_at=center.created_at)


async def _finish_delete(session: AsyncSession, stats: dict) -> dict:
    """Commit the row deletion, then remove the freed-up files from disk."""
    files = stats.pop("files", [])
    await session.commit()
    removed = await delete_files_now_unreferenced(session, files)
    return {"ok": True, **stats, "files_deleted": removed["deleted"]}


@router.delete("/centers/{center_id}")
async def remove_center(center_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    center = await session.get(AssessmentCenter, center_id)
    if center is None:
        raise HTTPException(status_code=404, detail="Центр не найден")
    return await _finish_delete(session, await delete_center(session, center_id))


@router.delete("/participants/{participant_id}")
async def remove_participant(
    participant_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    participant = await session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    return await _finish_delete(session, await delete_participants(session, [participant_id]))


@router.delete("/exercises/{exercise_id}")
async def remove_exercise(exercise_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    return await _finish_delete(session, await delete_exercises(session, [exercise_id]))


# ---- participants --------------------------------------------------------------------------

@router.post("/participants", response_model=ParticipantOut)
async def create_participant(
    payload: ParticipantCreate,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(current_user),
) -> ParticipantOut:
    center = await session.get(AssessmentCenter, payload.center_id)
    if center is None:
        raise HTTPException(status_code=404, detail="Центр не найден")

    participant = Participant(
        center_id=center.id,
        chat_id=WEB_OWNER_ID,
        user_id=user.id,
        full_name=(payload.code or "").strip(),
    )
    session.add(participant)
    await session.commit()
    await session.refresh(participant)

    if not participant.full_name:
        # Auto-assign a privacy-safe number once the row id is known.
        participant.full_name = f"№{participant.id}"
        await session.commit()
    return _participant_out(participant)


@router.get("/centers/{center_id}/participants", response_model=list[ParticipantOut])
async def list_participants(center_id: int, session: AsyncSession = Depends(get_session)) -> list[ParticipantOut]:
    rows = list(
        await session.scalars(
            select(Participant).where(Participant.center_id == center_id).order_by(Participant.id)
        )
    )
    ids = [p.id for p in rows] or [0]

    # Two grouped queries rather than per-participant lookups, so a large centre stays cheap.
    with_report = set(
        await session.scalars(
            select(ParticipantReport.participant_id).where(ParticipantReport.participant_id.in_(ids))
        )
    )
    processed = dict(
        (await session.execute(
            select(Exercise.participant_id, func.count(func.distinct(NotebookFillResult.exercise_id)))
            .join(NotebookFillResult, NotebookFillResult.exercise_id == Exercise.id)
            .where(Exercise.participant_id.in_(ids))
            .group_by(Exercise.participant_id)
        )).all()
    )
    return [
        _participant_out(p, has_report=p.id in with_report, processed=processed.get(p.id, 0))
        for p in rows
    ]


@router.get("/participants/{participant_id}", response_model=ParticipantOut)
async def get_participant(participant_id: int, session: AsyncSession = Depends(get_session)) -> ParticipantOut:
    participant = await session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    has_report, processed = await _participant_state(participant_id, session)
    return _participant_out(participant, has_report=has_report, processed=processed)


# ---- exercises -----------------------------------------------------------------------------

@router.post("/exercises", response_model=ExerciseOut)
async def create_exercise(
    payload: ExerciseCreate,
    session: AsyncSession = Depends(get_session),
    user: CurrentUser = Depends(current_user),
) -> ExerciseOut:
    participant = await session.get(Participant, payload.participant_id)
    if participant is None or participant.center_id != payload.center_id:
        raise HTTPException(status_code=404, detail="Участник не найден в этом центре")

    template = await session.get(ExerciseTemplate, payload.template_id)
    if template is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено в каталоге")
    if not template.is_usable:
        raise HTTPException(
            status_code=400,
            detail="Упражнение ещё не готово к использованию: нужен разбор ИИ, активация и блокнот.",
        )

    # Snapshot the context so past results stay reproducible if the catalog entry changes.
    # We store the compact understanding brief rather than the raw materials: this text is
    # resent in every analysis batch and role-labeling chunk (~7x per exercise), and the
    # brief carries exactly what scoring needs at a fraction of the size. Raw materials are
    # the fallback for entries that somehow have no card.
    context = render_understanding_brief(template.understanding_json, template.name)
    exercise = Exercise(
        center_id=payload.center_id,
        participant_id=payload.participant_id,
        chat_id=WEB_OWNER_ID,
        user_id=user.id,
        template_id=template.id,
        name=template.name,
        instructions_text=context or template.instructions_text,
    )
    session.add(exercise)
    await session.commit()
    await session.refresh(exercise)

    # The blank notebook comes from the catalog — downstream processing looks it up by exercise.
    session.add(
        ObserverNotebook(
            chat_id=WEB_OWNER_ID,
            user_id=WEB_OWNER_ID,
            exercise_id=exercise.id,
            file_id=f"template:{template.id}",
            file_name=template.notebook_file_name,
            file_path=template.notebook_path or "",
        )
    )
    await session.commit()
    return _exercise_out(exercise, template.notebook_indicator_count)


@router.get("/participants/{participant_id}/exercises", response_model=list[ExerciseOut])
async def list_exercises(participant_id: int, session: AsyncSession = Depends(get_session)) -> list[ExerciseOut]:
    rows = list(
        await session.scalars(
            select(Exercise).where(Exercise.participant_id == participant_id).order_by(Exercise.id)
        )
    )
    assessed = set(
        await session.scalars(
            select(NotebookFillResult.exercise_id).where(
                NotebookFillResult.exercise_id.in_([e.id for e in rows] or [0])
            )
        )
    )
    return [_exercise_out(e, has_result=e.id in assessed) for e in rows]


@router.get("/exercises/{exercise_id}", response_model=ExerciseOut)
async def get_exercise(exercise_id: int, session: AsyncSession = Depends(get_session)) -> ExerciseOut:
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    return _exercise_out(exercise)
