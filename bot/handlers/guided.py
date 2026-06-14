from __future__ import annotations

from html import escape
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.handlers.notebook import _download_notebook
from bot.handlers.workflow import (
    generate_ipr_document,
    prepare_participant_report,
    run_exercise_processing,
)
from bot.models import (
    AssessmentCenter,
    Exercise,
    InterviewRecord,
    MediaProcessingJob,
    ObserverNotebook,
    Participant,
)
from bot.services.observer_notebook import NotebookProcessingError, extract_notebook_indicators
from bot.services.telegram_files import extract_media_meta

logger = logging.getLogger(__name__)
router = Router()


class GuidedFlow(StatesGroup):
    center_name = State()
    participant_name = State()
    exercise_name = State()
    awaiting_audio = State()
    awaiting_notebook = State()


def _next_step_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Ещё упражнение", callback_data="guided:add_exercise")],
            [InlineKeyboardButton(text="📄 Сформировать отчёт", callback_data="guided:finish_report")],
        ]
    )


def _ipr_keyboard(participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="📋 Сформировать ИПР", callback_data=f"guided:make_ipr:{participant_id}")]]
    )


# ---- entry points from the welcome screen --------------------------------------------------

@router.callback_query(F.data == "guided:help")
async def cb_help(callback: CallbackQuery) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await callback.message.answer(
        "ℹ️ Как пользоваться ботом\n\n"
        "📝 Расшифровать запись — пришлите аудио, получите текст с разметкой ролей.\n\n"
        "📊 Оценить одно упражнение — бот проведёт по шагам: центр → участник → упражнение → "
        "аудио → блокнот наблюдателя (.xlsx), и выдаст заполненный блокнот, отчёт и ИПР.\n\n"
        "🏆 Оценить все упражнения — то же, но можно добавить несколько упражнений одному "
        "участнику; отчёт и ИПР построятся по всем сразу.\n\n"
        "На каждом шаге бот подсказывает, что отправить. Команды (/create_center и т.д.) тоже работают.\n\n"
        "Напишите /start, чтобы вернуться в меню."
    )


@router.callback_query(F.data == "guided:transcribe")
async def cb_transcribe(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await state.clear()
    await state.update_data(mode="transcribe")
    await state.set_state(GuidedFlow.awaiting_audio)
    await callback.answer()
    await callback.message.answer("🎙 Отправьте аудиозапись (голосовое, аудио или файл) — расшифрую её.")


@router.callback_query(F.data.in_({"guided:assess_single", "guided:assess_full"}))
async def cb_assess(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or not callback.data:
        return
    mode = "single" if callback.data.endswith("single") else "full"
    await state.clear()
    await state.update_data(mode=mode)
    await state.set_state(GuidedFlow.center_name)
    await callback.answer()
    await callback.message.answer("🏢 Введите название центра оценки:")


# ---- guided text steps ---------------------------------------------------------------------

@router.message(GuidedFlow.center_name, F.text)
async def step_center_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None or not (message.text or "").strip():
        await message.answer("Введите название центра текстом.")
        return
    center = AssessmentCenter(chat_id=message.chat.id, user_id=message.from_user.id, name=message.text.strip())
    session.add(center)
    await session.commit()
    await session.refresh(center)
    await state.update_data(center_id=center.id)
    await state.set_state(GuidedFlow.participant_name)
    await message.answer(f"✅ Центр «{center.name}» создан.\n\n👤 Введите ФИО участника:")


@router.message(GuidedFlow.participant_name, F.text)
async def step_participant_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None or not (message.text or "").strip():
        await message.answer("Введите ФИО участника текстом.")
        return
    data = await state.get_data()
    participant = Participant(
        center_id=int(data["center_id"]),
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        full_name=message.text.strip(),
    )
    session.add(participant)
    await session.commit()
    await session.refresh(participant)
    await state.update_data(participant_id=participant.id)
    await state.set_state(GuidedFlow.exercise_name)
    await message.answer(f"✅ Участник «{participant.full_name}» добавлен.\n\n📁 Введите название упражнения:")


@router.message(GuidedFlow.exercise_name, F.text)
async def step_exercise_name(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None or not (message.text or "").strip():
        await message.answer("Введите название упражнения текстом.")
        return
    data = await state.get_data()
    exercise = Exercise(
        center_id=int(data["center_id"]),
        participant_id=int(data["participant_id"]),
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        name=message.text.strip(),
    )
    session.add(exercise)
    await session.commit()
    await session.refresh(exercise)
    await state.update_data(exercise_id=exercise.id)
    await state.set_state(GuidedFlow.awaiting_audio)
    await message.answer(f"✅ Упражнение «{exercise.name}» создано.\n\n🎙 Отправьте аудиозапись этого упражнения:")


# ---- audio step ----------------------------------------------------------------------------

@router.message(GuidedFlow.awaiting_audio, F.voice | F.audio | F.document)
async def step_audio(message: Message, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None:
        return
    if message.document and (message.document.file_name or "").lower().endswith(".xlsx"):
        await message.answer("Сейчас нужна аудиозапись упражнения 🎙. Блокнот (.xlsx) отправите следующим шагом.")
        return
    if not settings.aitunnel_api_key:
        await message.answer("AI Tunnel API key не настроен на сервере.")
        return
    try:
        file_id, file_unique_id, file_type, file_size, file_name = extract_media_meta(message)
    except ValueError:
        await message.answer("Отправьте аудио (голосовое, аудио или аудиофайл).")
        return

    data = await state.get_data()
    mode = data.get("mode")
    exercise_id = int(data["exercise_id"]) if data.get("exercise_id") else None

    job = MediaProcessingJob(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        file_id=file_id,
        file_unique_id=file_unique_id,
        file_type=file_type,
        file_name=file_name,
        file_size=file_size,
        stt_provider="aitunnel",
        exercise_id=exercise_id if mode != "transcribe" else None,
        status="queued",
    )
    session.add(job)
    await session.commit()

    if mode == "transcribe":
        await state.clear()
        await message.answer(f"Задача #{job.id}: расшифровываю запись, пришлю результат.")
    else:
        await state.set_state(GuidedFlow.awaiting_notebook)
        await message.answer(
            f"Задача #{job.id}: расшифровываю запись и размечаю роли. "
            "Когда пришлю «готово» — отправьте блокнот наблюдателя по этому упражнению (.xlsx) 📊"
        )


# ---- notebook step -------------------------------------------------------------------------

@router.message(GuidedFlow.awaiting_notebook, F.document)
async def step_notebook(message: Message, bot: Bot, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None or message.document is None:
        return
    if not (message.document.file_name or "").lower().endswith(".xlsx"):
        await message.answer("Нужен файл блокнота наблюдателя в формате .xlsx.")
        return

    data = await state.get_data()
    exercise_id = int(data["exercise_id"]) if data.get("exercise_id") else None
    exercise = await session.get(Exercise, exercise_id) if exercise_id else None
    if exercise is None:
        await message.answer("Не нашёл активное упражнение. Начните заново: /start")
        await state.clear()
        return

    record = await session.scalar(
        select(InterviewRecord).where(InterviewRecord.exercise_id == exercise.id).order_by(InterviewRecord.id.desc())
    )
    if record is None:
        await message.answer("⏳ Ещё расшифровываю аудио. Подождите сообщение «готово» и отправьте блокнот снова.")
        return

    await message.answer("Получил блокнот наблюдателя. Сохраняю и обрабатываю...")
    try:
        local_path = await _download_notebook(bot, message)
        extract_notebook_indicators(local_path)
    except NotebookProcessingError as exc:
        await message.answer(f"Не удалось прочитать блокнот: {escape(str(exc), quote=False)}")
        return
    except Exception:
        logger.exception("Guided notebook upload failed")
        await message.answer("Ошибка при загрузке блокнота. Проверьте, что это .xlsx.")
        return

    notebook = ObserverNotebook(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        exercise_id=exercise.id,
        file_id=message.document.file_id,
        file_unique_id=message.document.file_unique_id,
        file_name=message.document.file_name,
        file_path=str(local_path),
    )
    session.add(notebook)
    await session.commit()

    ok = await run_exercise_processing(message, session, exercise)
    await state.set_state(None)
    if not ok:
        await message.answer(
            "Не удалось обработать упражнение. Можно попробовать отправить блокнот ещё раз "
            "или продолжить:",
            reply_markup=_next_step_keyboard(),
        )
        return
    await message.answer(
        "✅ Упражнение обработано.\n\n"
        "Дальше можно добавить ещё упражнение этому участнику или сразу сформировать отчёт "
        "(а затем ИПР).",
        reply_markup=_next_step_keyboard(),
    )


# ---- next-step callbacks -------------------------------------------------------------------

@router.callback_query(F.data == "guided:add_exercise")
async def cb_add_exercise(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    if not data.get("participant_id"):
        await callback.answer("Сессия не найдена, начните с /start", show_alert=True)
        return
    await state.set_state(GuidedFlow.exercise_name)
    await callback.answer()
    await callback.message.answer("📁 Введите название следующего упражнения:")


@router.callback_query(F.data == "guided:finish_report")
async def cb_finish_report(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    participant_id = int(data["participant_id"]) if data.get("participant_id") else None
    participant = await session.get(Participant, participant_id) if participant_id else None
    if participant is None:
        await callback.answer("Сессия не найдена, начните с /start", show_alert=True)
        return
    await callback.answer()
    ok = await prepare_participant_report(callback.message, session, participant)
    if ok:
        await callback.message.answer("Можно сформировать ИПР:", reply_markup=_ipr_keyboard(participant.id))


@router.callback_query(F.data.startswith("guided:make_ipr:"))
async def cb_make_ipr(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.message is None or callback.from_user is None or not callback.data:
        return
    participant_id = int(callback.data.split(":")[-1])
    participant = await session.scalar(
        select(Participant).where(Participant.id == participant_id, Participant.user_id == callback.from_user.id)
    )
    if participant is None:
        await callback.answer("Участник не найден", show_alert=True)
        return
    await callback.answer("Готовлю ИПР...")
    await generate_ipr_document(callback.message, session, participant)
