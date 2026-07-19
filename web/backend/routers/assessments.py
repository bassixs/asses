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
)
from bot.services.exercise_understanding import render_understanding_brief
from web.backend.deps import WEB_OWNER_ID, get_session
from web.backend.purge import delete_center, delete_exercises, delete_participants
from web.backend.schemas import (
    CenterCreate,
    CenterOut,
    ExerciseCreate,
    ExerciseOut,
    ParticipantCreate,
    ParticipantOut,
)

router = APIRouter(tags=["assessments"])


def _participant_out(participant: Participant) -> ParticipantOut:
    return ParticipantOut(id=participant.id, code=participant.full_name, center_id=participant.center_id)


def _exercise_out(exercise: Exercise, indicator_count: int | None = None) -> ExerciseOut:
    return ExerciseOut(
        id=exercise.id,
        name=exercise.name,
        participant_id=exercise.participant_id,
        center_id=exercise.center_id,
        has_instructions=bool(exercise.instructions_text),
        template_id=exercise.template_id,
        notebook_indicator_count=indicator_count,
    )


# ---- centers -------------------------------------------------------------------------------

@router.post("/centers", response_model=CenterOut)
async def create_center(payload: CenterCreate, session: AsyncSession = Depends(get_session)) -> CenterOut:
    center = AssessmentCenter(chat_id=WEB_OWNER_ID, user_id=WEB_OWNER_ID, name=payload.name.strip())
    session.add(center)
    await session.commit()
    await session.refresh(center)
    return CenterOut(id=center.id, name=center.name, created_at=center.created_at)


@router.get("/centers", response_model=list[CenterOut])
async def list_centers(session: AsyncSession = Depends(get_session)) -> list[CenterOut]:
    rows = list(await session.scalars(select(AssessmentCenter).order_by(AssessmentCenter.id.desc())))

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
        )
        for c in rows
    ]


@router.get("/centers/{center_id}", response_model=CenterOut)
async def get_center(center_id: int, session: AsyncSession = Depends(get_session)) -> CenterOut:
    center = await session.get(AssessmentCenter, center_id)
    if center is None:
        raise HTTPException(status_code=404, detail="Центр не найден")
    return CenterOut(id=center.id, name=center.name, created_at=center.created_at)


@router.delete("/centers/{center_id}")
async def remove_center(center_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    center = await session.get(AssessmentCenter, center_id)
    if center is None:
        raise HTTPException(status_code=404, detail="Центр не найден")
    stats = await delete_center(session, center_id)
    await session.commit()
    return {"ok": True, **stats}


@router.delete("/participants/{participant_id}")
async def remove_participant(
    participant_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    participant = await session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    stats = await delete_participants(session, [participant_id])
    await session.commit()
    return {"ok": True, **stats}


@router.delete("/exercises/{exercise_id}")
async def remove_exercise(exercise_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    stats = await delete_exercises(session, [exercise_id])
    await session.commit()
    return {"ok": True, **stats}


# ---- participants --------------------------------------------------------------------------

@router.post("/participants", response_model=ParticipantOut)
async def create_participant(
    payload: ParticipantCreate,
    session: AsyncSession = Depends(get_session),
) -> ParticipantOut:
    center = await session.get(AssessmentCenter, payload.center_id)
    if center is None:
        raise HTTPException(status_code=404, detail="Центр не найден")

    participant = Participant(
        center_id=center.id,
        chat_id=WEB_OWNER_ID,
        user_id=WEB_OWNER_ID,
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
    rows = await session.scalars(
        select(Participant).where(Participant.center_id == center_id).order_by(Participant.id)
    )
    return [_participant_out(p) for p in rows]


@router.get("/participants/{participant_id}", response_model=ParticipantOut)
async def get_participant(participant_id: int, session: AsyncSession = Depends(get_session)) -> ParticipantOut:
    participant = await session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    return _participant_out(participant)


# ---- exercises -----------------------------------------------------------------------------

@router.post("/exercises", response_model=ExerciseOut)
async def create_exercise(payload: ExerciseCreate, session: AsyncSession = Depends(get_session)) -> ExerciseOut:
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
        user_id=WEB_OWNER_ID,
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
    rows = await session.scalars(
        select(Exercise).where(Exercise.participant_id == participant_id).order_by(Exercise.id)
    )
    return [_exercise_out(e) for e in rows]


@router.get("/exercises/{exercise_id}", response_model=ExerciseOut)
async def get_exercise(exercise_id: int, session: AsyncSession = Depends(get_session)) -> ExerciseOut:
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    return _exercise_out(exercise)
