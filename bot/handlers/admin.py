from __future__ import annotations

from pathlib import Path
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import delete, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
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

router = Router()

_awaiting_password: set[int] = set()
_authenticated_admins: set[int] = set()


@router.message(Command("admin"))
async def cmd_admin(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    user_id = message.from_user.id
    if user_id in _authenticated_admins:
        await _send_admin_panel(message, session)
        return

    _awaiting_password.add(user_id)
    await message.answer("Введите пароль администратора:")


@router.message(F.text, lambda message: message.from_user and message.from_user.id in _awaiting_password)
async def admin_password_input(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        return

    user_id = message.from_user.id
    if (message.text or "").strip() != settings.admin_bot_password:
        await message.answer("Неверный пароль. Попробуйте ещё раз командой /admin.")
        _awaiting_password.discard(user_id)
        return

    _awaiting_password.discard(user_id)
    _authenticated_admins.add(user_id)
    await message.answer("Доступ открыт.")
    await _send_admin_panel(message, session)


@router.callback_query(F.data == "admin:panel")
async def callback_admin_panel(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _ensure_admin(callback):
        return
    text = await _admin_panel_text(session)
    await callback.message.edit_text(text, reply_markup=_admin_panel_keyboard())
    await callback.answer()


@router.callback_query(F.data.startswith("admin:list:"))
async def callback_admin_list(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _ensure_admin(callback):
        return

    kind = callback.data.split(":", maxsplit=2)[2]
    text, keyboard = await _list_text_and_keyboard(kind, session)
    await callback.message.edit_text(text, reply_markup=keyboard)
    await callback.answer()


@router.callback_query(F.data.startswith("admin:delete:"))
async def callback_admin_delete(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _ensure_admin(callback):
        return

    _, _, kind, raw_id = callback.data.split(":", maxsplit=3)
    deleted = await _delete_one(kind, int(raw_id), session)
    await session.commit()
    text = await _admin_panel_text(session)
    await callback.message.edit_text(f"{deleted}\n\n{text}", reply_markup=_admin_panel_keyboard())
    await callback.answer("Удалено")


@router.callback_query(F.data == "admin:confirm_all")
async def callback_admin_confirm_all(callback: CallbackQuery) -> None:
    if not await _ensure_admin(callback):
        return
    await callback.message.edit_text(
        "Удалить все записи, блокноты, оценки, заполненные файлы и локальные загруженные файлы?",
        reply_markup=InlineKeyboardMarkup(
            inline_keyboard=[
                [InlineKeyboardButton(text="Да, удалить всё", callback_data="admin:delete_all")],
                [InlineKeyboardButton(text="Назад", callback_data="admin:panel")],
            ]
        ),
    )
    await callback.answer()


@router.callback_query(F.data == "admin:delete_all")
async def callback_admin_delete_all(callback: CallbackQuery, session: AsyncSession) -> None:
    if not await _ensure_admin(callback):
        return

    await _delete_all(session)
    await session.commit()
    text = await _admin_panel_text(session)
    await callback.message.edit_text(f"Все загруженные данные удалены.\n\n{text}", reply_markup=_admin_panel_keyboard())
    await callback.answer("Готово")


async def _send_admin_panel(message: Message, session: AsyncSession) -> None:
    await message.answer(await _admin_panel_text(session), reply_markup=_admin_panel_keyboard())


async def _admin_panel_text(session: AsyncSession) -> str:
    counts = await _counts(session)
    return (
        "Админ-панель\n\n"
        f"Записи/транскрипты: {counts['records']}\n"
        f"Блокноты наблюдателя: {counts['notebooks']}\n"
        f"Оценки компетенций: {counts['assessments']}\n"
        f"Задачи обработки: {counts['jobs']}\n"
        f"Заполненные блокноты: {counts['fills']}\n"
        f"Центры/участники/упражнения: {counts['centers']}/{counts['participants']}/{counts['exercises']}\n"
        f"Файлов в uploads: {counts['upload_files']}\n"
        f"Файлов в reports: {counts['report_files']}"
    )


def _admin_panel_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="Записи", callback_data="admin:list:records"),
                InlineKeyboardButton(text="Блокноты", callback_data="admin:list:notebooks"),
            ],
            [
                InlineKeyboardButton(text="Оценки", callback_data="admin:list:assessments"),
                InlineKeyboardButton(text="Заполнения", callback_data="admin:list:fills"),
            ],
            [InlineKeyboardButton(text="Удалить всё", callback_data="admin:confirm_all")],
            [InlineKeyboardButton(text="Обновить", callback_data="admin:panel")],
        ]
    )


async def _list_text_and_keyboard(kind: str, session: AsyncSession) -> tuple[str, InlineKeyboardMarkup]:
    if kind == "records":
        items = list(await session.scalars(select(InterviewRecord).order_by(desc(InterviewRecord.created_at)).limit(10)))
        lines = ["Последние записи:"]
        buttons = []
        for item in items:
            lines.append(f"#{item.id}: user {item.user_id}, {item.file_type}, {len(item.transcript or '')} символов")
            buttons.append([InlineKeyboardButton(text=f"Удалить запись #{item.id}", callback_data=f"admin:delete:record:{item.id}")])
    elif kind == "notebooks":
        items = list(await session.scalars(select(ObserverNotebook).order_by(desc(ObserverNotebook.created_at)).limit(10)))
        lines = ["Последние блокноты:"]
        buttons = []
        for item in items:
            lines.append(f"#{item.id}: {item.file_name or 'без имени'}, user {item.user_id}")
            buttons.append([InlineKeyboardButton(text=f"Удалить блокнот #{item.id}", callback_data=f"admin:delete:notebook:{item.id}")])
    elif kind == "assessments":
        items = list(await session.scalars(select(AssessmentResult).order_by(desc(AssessmentResult.created_at)).limit(10)))
        lines = ["Последние оценки:"]
        buttons = []
        for item in items:
            lines.append(f"#{item.id}: запись #{item.record_id}, {item.summary or 'без summary'}")
            buttons.append([InlineKeyboardButton(text=f"Удалить оценку #{item.id}", callback_data=f"admin:delete:assessment:{item.id}")])
    elif kind == "fills":
        items = list(await session.scalars(select(NotebookFillResult).order_by(desc(NotebookFillResult.created_at)).limit(10)))
        lines = ["Последние заполненные блокноты:"]
        buttons = []
        for item in items:
            lines.append(f"#{item.id}: запись #{item.record_id}, блокнот #{item.notebook_id}")
            buttons.append([InlineKeyboardButton(text=f"Удалить заполнение #{item.id}", callback_data=f"admin:delete:fill:{item.id}")])
    else:
        lines = ["Неизвестный раздел."]
        buttons = []

    if len(lines) == 1:
        lines.append("Нет данных.")
    buttons.append([InlineKeyboardButton(text="Назад", callback_data="admin:panel")])
    return "\n".join(lines), InlineKeyboardMarkup(inline_keyboard=buttons)


async def _counts(session: AsyncSession) -> dict[str, int]:
    return {
        "records": await session.scalar(select(func.count(InterviewRecord.id))) or 0,
        "notebooks": await session.scalar(select(func.count(ObserverNotebook.id))) or 0,
        "assessments": await session.scalar(select(func.count(AssessmentResult.id))) or 0,
        "jobs": await session.scalar(select(func.count(MediaProcessingJob.id))) or 0,
        "fills": await session.scalar(select(func.count(NotebookFillResult.id))) or 0,
        "centers": await session.scalar(select(func.count(AssessmentCenter.id))) or 0,
        "participants": await session.scalar(select(func.count(Participant.id))) or 0,
        "exercises": await session.scalar(select(func.count(Exercise.id))) or 0,
        "upload_files": _count_files(settings.download_dir),
        "report_files": _count_files(settings.download_dir.parent / "reports"),
    }


async def _delete_one(kind: str, item_id: int, session: AsyncSession) -> str:
    if kind == "record":
        record = await session.get(InterviewRecord, item_id)
        if record is None:
            return "Запись не найдена."
        await _delete_record(session, record)
        return f"Запись #{item_id} удалена."

    if kind == "notebook":
        notebook = await session.get(ObserverNotebook, item_id)
        if notebook is None:
            return "Блокнот не найден."
        await _delete_notebook(session, notebook)
        return f"Блокнот #{item_id} удален."

    if kind == "assessment":
        assessment = await session.get(AssessmentResult, item_id)
        if assessment is None:
            return "Оценка не найдена."
        await session.delete(assessment)
        return f"Оценка #{item_id} удалена."

    if kind == "fill":
        fill = await session.get(NotebookFillResult, item_id)
        if fill is None:
            return "Заполнение не найдено."
        _safe_unlink(fill.output_path)
        await session.delete(fill)
        return f"Заполнение #{item_id} удалено."

    return "Неизвестный тип удаления."


async def _delete_all(session: AsyncSession) -> None:
    for record in list(await session.scalars(select(InterviewRecord))):
        _safe_unlink(record.file_path)
    for notebook in list(await session.scalars(select(ObserverNotebook))):
        _safe_unlink(notebook.file_path)
    for fill in list(await session.scalars(select(NotebookFillResult))):
        _safe_unlink(fill.output_path)

    await session.execute(delete(NotebookFillResult))
    await session.execute(delete(AssessmentResult))
    await session.execute(delete(DevelopmentPlan))
    await session.execute(delete(ParticipantReport))
    await session.execute(delete(MediaProcessingJob))
    await session.execute(delete(ObserverNotebook))
    await session.execute(delete(InterviewRecord))
    await session.execute(delete(Exercise))
    await session.execute(delete(Participant))
    await session.execute(delete(AssessmentCenter))
    _delete_runtime_files(settings.download_dir)
    _delete_runtime_files(settings.download_dir.parent / "reports")


async def _delete_record(session: AsyncSession, record: InterviewRecord) -> None:
    for fill in list(await session.scalars(select(NotebookFillResult).where(NotebookFillResult.record_id == record.id))):
        _safe_unlink(fill.output_path)
        await session.delete(fill)
    await session.execute(delete(AssessmentResult).where(AssessmentResult.record_id == record.id))
    _safe_unlink(record.file_path)
    await session.delete(record)


async def _delete_notebook(session: AsyncSession, notebook: ObserverNotebook) -> None:
    for fill in list(
        await session.scalars(select(NotebookFillResult).where(NotebookFillResult.notebook_id == notebook.id))
    ):
        _safe_unlink(fill.output_path)
        await session.delete(fill)
    _safe_unlink(notebook.file_path)
    await session.delete(notebook)


async def _ensure_admin(callback: CallbackQuery) -> bool:
    if callback.from_user.id not in _authenticated_admins:
        await callback.answer("Сначала войдите через /admin", show_alert=True)
        return False
    if callback.message is None:
        await callback.answer("Сообщение недоступно", show_alert=True)
        return False
    return True


def _count_files(directory: Path) -> int:
    if not directory.exists():
        return 0
    return sum(1 for item in directory.iterdir() if item.is_file())


def _safe_unlink(path: str | None) -> None:
    if not path:
        return
    file_path = _resolve_runtime_path(path)
    data_root = (Path.cwd() / "data").resolve()
    try:
        file_path.relative_to(data_root)
    except ValueError:
        return
    if file_path.exists() and file_path.is_file():
        file_path.unlink()


def _delete_runtime_files(directory: Path) -> None:
    if not directory.exists():
        return
    data_root = (Path.cwd() / "data").resolve()
    try:
        directory.resolve().relative_to(data_root)
    except ValueError:
        return
    for item in directory.iterdir():
        if item.is_file():
            item.unlink()


def _resolve_runtime_path(path: str) -> Path:
    file_path = Path(path)
    if not file_path.is_absolute():
        file_path = Path.cwd() / file_path
    return file_path.resolve()
