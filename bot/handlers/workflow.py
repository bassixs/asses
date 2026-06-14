from __future__ import annotations

import asyncio
import json
import logging
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot
from aiogram import Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.database import async_session_maker
from bot.models import (
    AssessmentCenter,
    DevelopmentPlan,
    Exercise,
    InterviewRecord,
    NotebookFillResult,
    ObserverNotebook,
    Participant,
    ParticipantReport,
)
from bot.services.development_advice import enrich_competencies_with_advice
from bot.services.llm_json import LLMJSONError
from bot.services.pdf_export import convert_to_pdf
from bot.services.observer_notebook import (
    NotebookProcessingError,
    analyze_notebook_indicators,
    attach_evidence_timestamps,
    extract_notebook_indicators,
    fill_observer_notebook,
)
from bot.services.reports import (
    build_development_plan_text,
    build_participant_report_text,
    save_development_plan_docx,
    save_participant_report_docx,
)
from bot.services.role_labeling import RoleLabelingError, label_transcript_roles
from bot.services.transcript_export import build_transcript_text_file

router = Router()


@router.message(Command("create_center"))
async def cmd_create_center(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    name = _command_arg(message)
    if not name:
        await message.answer("Напишите название: /create_center Резерв руководителей май 2026")
        return
    center = AssessmentCenter(chat_id=message.chat.id, user_id=message.from_user.id, name=name)
    session.add(center)
    await session.commit()
    await session.refresh(center)
    await message.answer(f"Создан ассессмент-центр #{center.id}: {center.name}")


@router.message(Command("add_participant"))
async def cmd_add_participant(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    parsed = _parse_id_and_text(message)
    if parsed is None:
        await message.answer("Формат: /add_participant <center_id> Иван Петров")
        return
    center_id, full_name = parsed
    center = await _load_center(session, center_id, message.from_user.id)
    if center is None:
        await message.answer("Ассессмент-центр не найден.")
        return
    participant = Participant(
        center_id=center.id,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        full_name=full_name,
    )
    session.add(participant)
    await session.commit()
    await session.refresh(participant)
    await message.answer(f"Создан участник #{participant.id}: {participant.full_name}")


@router.message(Command("add_exercise"))
async def cmd_add_exercise(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    parsed = _parse_id_and_text(message)
    if parsed is None:
        await message.answer("Формат: /add_exercise <participant_id> Ролевая встреча")
        return
    participant_id, name = parsed
    participant = await _load_participant(session, participant_id, message.from_user.id)
    if participant is None:
        await message.answer("Участник не найден.")
        return
    exercise = Exercise(
        center_id=participant.center_id,
        participant_id=participant.id,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=name,
    )
    session.add(exercise)
    await session.commit()
    await session.refresh(exercise)
    await message.answer(f"Создано упражнение #{exercise.id}: {exercise.name}")


@router.message(Command("centers"))
async def cmd_centers(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    centers = list(
        await session.scalars(
            select(AssessmentCenter).where(AssessmentCenter.user_id == message.from_user.id).order_by(AssessmentCenter.id)
        )
    )
    if not centers:
        await message.answer("Ассессмент-центров пока нет. Создайте: /create_center Название")
        return
    await message.answer("Ассессмент-центры:\n" + "\n".join(f"#{item.id}: {item.name}" for item in centers))


@router.message(Command("participants"))
async def cmd_participants(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    center_id = _single_id_arg(message)
    if center_id is None:
        await message.answer("Формат: /participants <center_id>")
        return
    participants = list(
        await session.scalars(
            select(Participant)
            .where(Participant.center_id == center_id, Participant.user_id == message.from_user.id)
            .order_by(Participant.id)
        )
    )
    if not participants:
        await message.answer("Участников пока нет.")
        return
    await message.answer("Участники:\n" + "\n".join(f"#{item.id}: {item.full_name}" for item in participants))


@router.message(Command("exercises"))
async def cmd_exercises(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    participant_id = _single_id_arg(message)
    if participant_id is None:
        await message.answer("Формат: /exercises <participant_id>")
        return
    exercises = list(
        await session.scalars(
            select(Exercise)
            .where(Exercise.participant_id == participant_id, Exercise.user_id == message.from_user.id)
            .order_by(Exercise.id)
        )
    )
    if not exercises:
        await message.answer("Упражнений пока нет.")
        return
    await message.answer("Упражнения:\n" + "\n".join(f"#{item.id}: {item.name}" for item in exercises))


@router.message(Command("attach_record"))
async def cmd_attach_record(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    parsed = _parse_two_ids(message)
    if parsed is None:
        await message.answer("Формат: /attach_record <exercise_id> <record_id>")
        return
    exercise_id, record_id = parsed
    exercise = await _load_exercise(session, exercise_id, message.from_user.id)
    record = await session.scalar(
        select(InterviewRecord).where(InterviewRecord.id == record_id, InterviewRecord.user_id == message.from_user.id)
    )
    if exercise is None or record is None:
        await message.answer("Упражнение или запись не найдены.")
        return
    record.exercise_id = exercise.id
    await session.commit()
    await message.answer(f"Запись #{record.id} привязана к упражнению #{exercise.id}. Уточняю роли по участнику упражнения...")
    asyncio.create_task(_relabel_record_roles_after_attach(
        bot=bot,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        record_id=record.id,
        exercise_id=exercise.id,
    ))


async def _relabel_record_roles_after_attach(
    *,
    bot: Bot,
    chat_id: int,
    user_id: int,
    record_id: int,
    exercise_id: int,
) -> None:
    async with async_session_maker() as session:
        exercise = await session.get(Exercise, exercise_id)
        record = await session.scalar(
            select(InterviewRecord).where(InterviewRecord.id == record_id, InterviewRecord.user_id == user_id)
        )
        if exercise is None or record is None:
            await bot.send_message(chat_id, "Не удалось переуточнить роли: упражнение или запись не найдены.")
            return

        participant = await session.get(Participant, exercise.participant_id)
        try:
            source_transcript = record.raw_transcript or record.transcript
            record.transcript = await label_transcript_roles(
                source_transcript,
                assessed_participant_name=participant.full_name if participant else None,
                exercise_name=exercise.name,
            )
            transcript_path = await build_transcript_text_file(transcript=record.transcript, record_id=record.id)
            record.transcript_file_path = str(transcript_path)
            await session.commit()
            await bot.send_message(
                chat_id,
                f"Роли в записи #{record.id} обновлены с учетом оцениваемого участника"
                f"{f' ({participant.full_name})' if participant else ''}.",
            )
        except RoleLabelingError as exc:
            await session.commit()
            await bot.send_message(
                chat_id,
                f"Запись привязана, но роли не удалось переуточнить автоматически: {escape(str(exc), quote=False)}",
            )


@router.message(Command("attach_notebook"))
async def cmd_attach_notebook(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    parsed = _parse_two_ids(message)
    if parsed is None:
        await message.answer("Формат: /attach_notebook <exercise_id> <notebook_id>")
        return
    exercise_id, notebook_id = parsed
    exercise = await _load_exercise(session, exercise_id, message.from_user.id)
    notebook = await session.scalar(
        select(ObserverNotebook).where(ObserverNotebook.id == notebook_id, ObserverNotebook.user_id == message.from_user.id)
    )
    if exercise is None or notebook is None:
        await message.answer("Упражнение или блокнот не найдены.")
        return
    notebook.exercise_id = exercise.id
    await session.commit()
    await message.answer(f"Блокнот #{notebook.id} привязан к упражнению #{exercise.id}.")


@router.message(Command("process_exercise"))
async def cmd_process_exercise(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    exercise_id = _single_id_arg(message)
    if exercise_id is None:
        await message.answer("Формат: /process_exercise <exercise_id>")
        return
    exercise = await _load_exercise(session, exercise_id, message.from_user.id)
    if exercise is None:
        await message.answer("Упражнение не найдено.")
        return
    record = await session.scalar(
        select(InterviewRecord).where(InterviewRecord.exercise_id == exercise.id).order_by(InterviewRecord.id.desc())
    )
    notebook = await session.scalar(
        select(ObserverNotebook).where(ObserverNotebook.exercise_id == exercise.id).order_by(ObserverNotebook.id.desc())
    )
    if record is None or notebook is None:
        await message.answer("К упражнению нужно привязать запись и блокнот.")
        return

    await message.answer("Обрабатываю упражнение: заполняю блокнот наблюдателя...")
    input_path = Path(notebook.file_path)
    indicators = extract_notebook_indicators(input_path)
    try:
        report = await analyze_notebook_indicators(transcript=record.transcript, indicators=indicators)
    except (NotebookProcessingError, LLMJSONError) as exc:
        logging.getLogger(__name__).exception("process_exercise analysis failed for exercise_id=%s", exercise.id)
        await message.answer(f"Не удалось обработать упражнение #{exercise.id}: {escape(str(exc), quote=False)}")
        return
    attach_evidence_timestamps(report, _load_segments(record.transcript_segments))
    output_path = settings.download_dir.parent / "reports" / f"exercise_{exercise.id}_filled.xlsx"
    result_json = fill_observer_notebook(
        input_path=input_path,
        output_path=output_path,
        indicators=indicators,
        report=report,
    )
    fill_result = NotebookFillResult(
        exercise_id=exercise.id,
        record_id=record.id,
        notebook_id=notebook.id,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        output_path=str(output_path),
        result_json=result_json,
    )
    session.add(fill_result)
    await session.commit()
    await message.answer_document(FSInputFile(output_path), caption=f"Готово: упражнение #{exercise.id} обработано.")


@router.message(Command("generate_report"))
async def cmd_generate_report(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    participant_id = _single_id_arg(message)
    if participant_id is None:
        await message.answer("Формат: /generate_report <participant_id>")
        return
    participant = await _load_participant(session, participant_id, message.from_user.id)
    if participant is None:
        await message.answer("Участник не найден.")
        return
    fills = list(
        await session.scalars(
            select(NotebookFillResult)
            .join(Exercise, NotebookFillResult.exercise_id == Exercise.id)
            .where(Exercise.participant_id == participant.id)
            .order_by(NotebookFillResult.id)
        )
    )
    if not fills:
        await message.answer("Нет обработанных упражнений для отчета.")
        return
    _, result_json = build_participant_report_text(
        participant_name=participant.full_name,
        exercise_results=[item.result_json for item in fills],
    )
    await message.answer("Формирую отчёт и персональные рекомендации...")
    await enrich_competencies_with_advice(
        result_json.get("competencies", {}),
        participant_name=participant.full_name,
    )
    exercises = list(
        await session.scalars(
            select(Exercise).where(Exercise.participant_id == participant.id).order_by(Exercise.id)
        )
    )
    center = await session.get(AssessmentCenter, participant.center_id)
    output_path = settings.download_dir.parent / "reports" / f"participant_{participant.id}_report.docx"
    save_participant_report_docx(
        path=output_path,
        participant_name=participant.full_name,
        center_name=center.name if center else None,
        exercise_names=[item.name for item in exercises],
        report_json=result_json,
    )
    report = ParticipantReport(
        participant_id=participant.id,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        output_path=str(output_path),
        result_json=result_json,
    )
    session.add(report)
    await session.commit()
    await _send_docx_with_pdf(message, output_path, caption=f"Отчет участника #{participant.id} сформирован.")


@router.message(Command("generate_ipr"))
async def cmd_generate_ipr(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return
    participant_id = _single_id_arg(message)
    if participant_id is None:
        await message.answer("Формат: /generate_ipr <participant_id>")
        return
    participant = await _load_participant(session, participant_id, message.from_user.id)
    if participant is None:
        await message.answer("Участник не найден.")
        return
    report = await session.scalar(
        select(ParticipantReport)
        .where(ParticipantReport.participant_id == participant.id)
        .order_by(ParticipantReport.id.desc())
    )
    if report is None:
        await message.answer("Сначала сформируйте отчет: /generate_report <participant_id>")
        return
    _, result_json = build_development_plan_text(
        participant_name=participant.full_name,
        report_json=report.result_json,
    )
    center = await session.get(AssessmentCenter, participant.center_id)
    output_path = settings.download_dir.parent / "reports" / f"participant_{participant.id}_ipr.docx"
    save_development_plan_docx(
        path=output_path,
        participant_name=participant.full_name,
        center_name=center.name if center else None,
        plan_json=result_json,
    )
    plan = DevelopmentPlan(
        participant_id=participant.id,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        output_path=str(output_path),
        result_json=result_json,
    )
    session.add(plan)
    await session.commit()
    await _send_docx_with_pdf(message, output_path, caption=f"ИПР участника #{participant.id} сформирован.")


def _load_segments(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


async def _send_docx_with_pdf(message: Message, docx_path: Path, *, caption: str) -> None:
    await message.answer_document(FSInputFile(docx_path), caption=caption)
    try:
        pdf_path = await convert_to_pdf(docx_path)
    except Exception:  # noqa: BLE001 - PDF is a bonus, never block the docx delivery
        logging.getLogger(__name__).exception("PDF conversion crashed for %s", docx_path)
        pdf_path = None
    if pdf_path is not None:
        await message.answer_document(FSInputFile(pdf_path), caption="PDF-версия")


def _command_arg(message: Message) -> str:
    return (message.text or "").split(maxsplit=1)[1].strip() if len((message.text or "").split(maxsplit=1)) > 1 else ""


def _parse_id_and_text(message: Message) -> tuple[int, str] | None:
    parts = (message.text or "").split(maxsplit=2)
    if len(parts) != 3 or not parts[1].isdigit():
        return None
    return int(parts[1]), parts[2].strip()


def _single_id_arg(message: Message) -> int | None:
    parts = (message.text or "").split(maxsplit=1)
    return int(parts[1]) if len(parts) == 2 and parts[1].isdigit() else None


def _parse_two_ids(message: Message) -> tuple[int, int] | None:
    parts = (message.text or "").split()
    if len(parts) != 3 or not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


async def _load_center(session: AsyncSession, center_id: int, user_id: int) -> AssessmentCenter | None:
    return await session.scalar(
        select(AssessmentCenter).where(AssessmentCenter.id == center_id, AssessmentCenter.user_id == user_id)
    )


async def _load_participant(session: AsyncSession, participant_id: int, user_id: int) -> Participant | None:
    return await session.scalar(
        select(Participant).where(Participant.id == participant_id, Participant.user_id == user_id)
    )


async def _load_exercise(session: AsyncSession, exercise_id: int, user_id: int) -> Exercise | None:
    return await session.scalar(select(Exercise).where(Exercise.id == exercise_id, Exercise.user_id == user_id))
