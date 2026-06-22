from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from html import escape
from pathlib import Path
from typing import Any

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
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
from bot.services.observer_notebook import (
    NotebookProcessingError,
    analyze_notebook_indicators,
    attach_evidence_timestamps,
    extract_notebook_indicators,
    fill_observer_notebook,
    verify_evidence_quotes,
)
from bot.services.telegram_files import send_document_with_retry
from bot.services.reports import (
    build_development_plan_text,
    build_participant_report_text,
    save_development_plan_docx,
    save_participant_report_docx,
)
from bot.services.role_labeling import RoleLabelingError, label_transcript_roles
from bot.services.transcript_export import build_transcript_text_file
from bot.keyboards import report_format_keyboard

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
        await message.answer("Формат: /add_participant <center_id> <код участника без ФИО>")
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
    await run_exercise_processing(message, session, exercise)


async def run_exercise_processing(message: Message, session: AsyncSession, exercise: Exercise) -> bool:
    """Analyse the latest record+notebook of an exercise, fill the notebook, send it. Returns success."""
    record = await session.scalar(
        select(InterviewRecord).where(InterviewRecord.exercise_id == exercise.id).order_by(InterviewRecord.id.desc())
    )
    notebook = await session.scalar(
        select(ObserverNotebook).where(ObserverNotebook.exercise_id == exercise.id).order_by(ObserverNotebook.id.desc())
    )
    if record is None or notebook is None:
        await message.answer("К упражнению нужно привязать запись и блокнот.")
        return False

    await message.answer("Обрабатываю упражнение: заполняю блокнот наблюдателя...")
    input_path = Path(notebook.file_path)
    indicators = extract_notebook_indicators(input_path)
    try:
        report = await analyze_notebook_indicators(
            transcript=record.transcript,
            indicators=indicators,
            exercise_name=exercise.name,
            exercise_instructions=exercise.instructions_text,
        )
    except (NotebookProcessingError, LLMJSONError) as exc:
        logging.getLogger(__name__).exception("process_exercise analysis failed for exercise_id=%s", exercise.id)
        await message.answer(f"Не удалось обработать упражнение #{exercise.id}: {escape(str(exc), quote=False)}")
        return False
    verify_evidence_quotes(report, record.transcript)
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
    await send_document_with_retry(
        message.bot,
        message.chat.id,
        output_path,
        caption=f"Готово: упражнение «{exercise.name}» обработано.",
    )
    return True


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
    await prepare_participant_report(message, session, participant)


async def prepare_participant_report(message: Message, session: AsyncSession, participant: Participant) -> bool:
    """Build, enrich and store a participant report, then offer format buttons. Returns success."""
    fills = list(
        await session.scalars(
            select(NotebookFillResult)
            .join(Exercise, NotebookFillResult.exercise_id == Exercise.id)
            .where(Exercise.participant_id == participant.id)
            .order_by(NotebookFillResult.id)
        )
    )
    if not fills:
        await message.answer("Нет обработанных упражнений для отчёта.")
        return False
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
    exercise_by_id = {item.id: item.name for item in exercises}
    result_json["participant_name"] = participant.full_name
    result_json["center_name"] = center.name if center else None
    result_json["exercise_names"] = [item.name for item in exercises]
    result_json["matrix"] = _build_competency_matrix(fills, exercise_by_id)
    result_json["generated_date"] = datetime.now().strftime("%d.%m.%Y")

    report = ParticipantReport(
        participant_id=participant.id,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        output_path="",
        result_json=result_json,
    )
    session.add(report)
    await session.commit()
    await message.answer(
        f"Отчёт участника «{participant.full_name}» готов. В каком формате выдать?",
        reply_markup=report_format_keyboard(participant.id),
    )
    return True


def _build_competency_matrix(fills: list[Any], exercise_by_id: dict[int, str]) -> dict[str, dict[str, Any]]:
    matrix: dict[str, dict[str, Any]] = {}
    for fill in fills:
        exercise_name = exercise_by_id.get(fill.exercise_id, f"Упражнение {fill.exercise_id}")
        levels = (fill.result_json or {}).get("levels", {}) or {}
        for competence, level_data in levels.items():
            level = level_data.get("level") if isinstance(level_data, dict) else level_data
            matrix.setdefault(str(competence), {})[exercise_name] = level
    return matrix


class ReportFormatUnavailable(RuntimeError):
    pass


@router.callback_query(F.data.startswith("report_format:"))
async def callback_report_format(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None or not callback.data:
        return
    _, raw_participant_id, fmt = callback.data.split(":", maxsplit=2)
    participant_id = int(raw_participant_id)
    participant = await _load_participant(session, participant_id, callback.from_user.id)
    if participant is None:
        await callback.answer("Участник не найден.", show_alert=True)
        return
    report = await session.scalar(
        select(ParticipantReport)
        .where(ParticipantReport.participant_id == participant_id)
        .order_by(ParticipantReport.id.desc())
    )
    if report is None:
        await callback.answer("Сначала сформируйте отчёт: /generate_report", show_alert=True)
        return

    await callback.answer(f"Готовлю {fmt.upper()}...")
    try:
        document = await asyncio.to_thread(_render_report_base, participant_id, fmt, report.result_json)
    except ReportFormatUnavailable as exc:
        await callback.message.answer(str(exc))
        return
    except Exception:
        logging.getLogger(__name__).exception("Report rendering failed for participant_id=%s fmt=%s", participant_id, fmt)
        await callback.message.answer("Не удалось сформировать файл отчёта.")
        return

    await send_document_with_retry(
        callback.message.bot,
        callback.message.chat.id,
        document,
        caption=f"Отчёт участника #{participant_id} ({fmt.upper()}).",
    )


def _render_report_base(participant_id: int, base_fmt: str, result_json: dict[str, Any]) -> Path:
    reports_dir = settings.download_dir.parent / "reports"
    name = result_json.get("participant_name") or ""
    center = result_json.get("center_name")
    exercise_names = result_json.get("exercise_names") or []

    if base_fmt == "docx":
        out = reports_dir / f"participant_{participant_id}_report.docx"
        save_participant_report_docx(
            path=out, participant_name=name, center_name=center,
            exercise_names=exercise_names, report_json=result_json,
        )
        return out

    try:
        from bot.services.report_pptx import save_participant_report_pptx
    except ImportError as exc:
        raise ReportFormatUnavailable(
            "Для PPTX/PDF нужен пакет python-pptx на сервере (pip install python-pptx).",
        ) from exc

    out = reports_dir / f"participant_{participant_id}_report.pptx"
    save_participant_report_pptx(
        path=out, participant_name=name, center_name=center,
        exercise_names=exercise_names, report_json=result_json,
    )
    return out


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
    await generate_ipr_document(message, session, participant)


async def generate_ipr_document(message: Message, session: AsyncSession, participant: Participant) -> bool:
    """Build the IPR docx from the latest report and send it as DOCX + PDF. Returns success."""
    report = await session.scalar(
        select(ParticipantReport)
        .where(ParticipantReport.participant_id == participant.id)
        .order_by(ParticipantReport.id.desc())
    )
    if report is None:
        await message.answer("Сначала сформируйте отчёт.")
        return False
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
    await send_document_with_retry(
        message.bot,
        message.chat.id,
        output_path,
        caption=f"ИПР участника «{participant.full_name}» сформирован.",
    )
    return True


def _load_segments(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


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
