from __future__ import annotations

from html import escape
import logging
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramNetworkError
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import (
    CallbackQuery,
    ErrorEvent,
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    Message,
)
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.keyboards import welcome_keyboard
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
from bot.services.instruction_files import (
    InstructionExtractionError,
    append_instructions,
    extract_instruction_text,
    is_supported_instruction,
)
from bot.services.observer_notebook import NotebookProcessingError, extract_notebook_indicators
from bot.services.telegram_files import download_telegram_file, extract_media_meta

logger = logging.getLogger(__name__)
router = Router()


class GuidedFlow(StatesGroup):
    center_name = State()
    participant_name = State()
    exercise_name = State()
    awaiting_instructions = State()
    awaiting_audio = State()
    awaiting_notebook = State()


_MENU_ROW = [InlineKeyboardButton(text="🏠 В меню", callback_data="guided:home")]


def _instructions_keyboard(has_files: bool) -> InlineKeyboardMarkup:
    next_text = "➡️ Дальше, к аудио" if has_files else "⏭ Пропустить (без инструкций)"
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text=next_text, callback_data="guided:instructions_done")],
            _MENU_ROW,
        ]
    )


_INSTRUCTIONS_PROMPT = (
    "📎 Пришлите инструкции к этому упражнению (PDF или DOCX) — материалы ведущего, "
    "наблюдателя/ролевого игрока и участника. Можно несколько файлов по очереди.\n\n"
    "Они помогают точнее определить роли и понять, какие индикаторы могли наблюдаться "
    "(для «НЗ»). Если инструкций нет — нажмите «Пропустить»."
)


async def _go_to_audio(message: Message, state: FSMContext) -> None:
    await state.set_state(GuidedFlow.awaiting_audio)
    await message.answer(
        "🎙 Отправьте аудиозапись этого упражнения:",
        reply_markup=_menu_keyboard(),
    )


def _next_step_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="➕ Ещё упражнение", callback_data="guided:add_exercise")],
            [InlineKeyboardButton(text="📄 Сформировать отчёт", callback_data="guided:finish_report")],
            _MENU_ROW,
        ]
    )


def _retry_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="🔄 Попробовать ещё раз", callback_data="guided:retry")],
            _MENU_ROW,
        ]
    )


def _menu_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[_MENU_ROW])


def _ipr_keyboard(participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="📋 Сформировать ИПР", callback_data=f"guided:make_ipr:{participant_id}")],
            _MENU_ROW,
        ]
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
        "инструкции упражнения (PDF/DOCX, по желанию) → аудио → блокнот наблюдателя (.xlsx), "
        "и выдаст заполненный блокнот, отчёт и ИПР.\n\n"
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
    await callback.message.answer(
        "🎙 Отправьте аудиозапись (голосовое, аудио или файл) — расшифрую её.",
        reply_markup=_menu_keyboard(),
    )


@router.callback_query(F.data.in_({"guided:assess_single", "guided:assess_full"}))
async def cb_assess(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None or not callback.data:
        return
    mode = "single" if callback.data.endswith("single") else "full"
    await state.clear()
    await state.update_data(mode=mode)
    await state.set_state(GuidedFlow.center_name)
    await callback.answer()
    await callback.message.answer("🏢 Введите название центра оценки:", reply_markup=_menu_keyboard())


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
    await message.answer(
        f"✅ Центр «{center.name}» создан.\n\n👤 Введите ФИО участника:",
        reply_markup=_menu_keyboard(),
    )


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
    await message.answer(
        f"✅ Участник «{participant.full_name}» добавлен.\n\n📁 Введите название упражнения:",
        reply_markup=_menu_keyboard(),
    )


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
    await state.set_state(GuidedFlow.awaiting_instructions)
    await message.answer(
        f"✅ Упражнение «{exercise.name}» создано.\n\n{_INSTRUCTIONS_PROMPT}",
        reply_markup=_instructions_keyboard(has_files=False),
    )


# ---- instructions step ---------------------------------------------------------------------

@router.message(GuidedFlow.awaiting_instructions, F.document)
async def step_instructions(message: Message, bot: Bot, session: AsyncSession, state: FSMContext) -> None:
    if message.from_user is None or message.document is None:
        return
    file_name = message.document.file_name or "instruction"
    if not is_supported_instruction(file_name):
        await message.answer(
            "Нужен файл инструкции в формате PDF или DOCX. "
            "Пришлите такой файл или нажмите «Пропустить».",
            reply_markup=_instructions_keyboard(has_files=False),
        )
        return

    data = await state.get_data()
    exercise_id = int(data["exercise_id"]) if data.get("exercise_id") else None
    exercise = await session.get(Exercise, exercise_id) if exercise_id else None
    if exercise is None:
        await state.clear()
        await message.answer("Не нашёл активное упражнение. Начните заново.", reply_markup=_menu_keyboard())
        return

    await message.answer(f"Принял «{escape(file_name, quote=False)}», читаю...")
    try:
        local_path = await download_telegram_file(bot, message.document.file_id, "instruction", file_name)
        text = extract_instruction_text(local_path)
    except InstructionExtractionError as exc:
        await message.answer(
            f"Не удалось прочитать файл: {escape(str(exc), quote=False)}\n"
            "Пришлите другой файл или нажмите «Пропустить».",
            reply_markup=_instructions_keyboard(has_files=bool(exercise.instructions_text)),
        )
        return
    except Exception:
        logger.exception("Guided instruction upload failed")
        await message.answer(
            "Ошибка при загрузке файла (возможно, связь с Telegram). Пришлите файл ещё раз.",
            reply_markup=_instructions_keyboard(has_files=bool(exercise.instructions_text)),
        )
        return

    exercise.instructions_text = append_instructions(exercise.instructions_text, text, source=file_name)
    await session.commit()
    await message.answer(
        f"✅ Инструкция добавлена ({len(text)} символов). "
        "Пришлите ещё файл или нажмите «Дальше, к аудио».",
        reply_markup=_instructions_keyboard(has_files=True),
    )


@router.message(GuidedFlow.awaiting_instructions, F.text)
async def step_instructions_text(message: Message, state: FSMContext) -> None:
    data = await state.get_data()
    has_files = bool(data.get("exercise_id"))
    await message.answer(
        "Жду файл инструкции (PDF или DOCX). Если инструкций нет — нажмите кнопку ниже.",
        reply_markup=_instructions_keyboard(has_files=has_files),
    )


@router.callback_query(GuidedFlow.awaiting_instructions, F.data == "guided:instructions_done")
async def cb_instructions_done(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await callback.answer()
    await _go_to_audio(callback.message, state)


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
        await message.answer(
            f"Задача #{job.id}: расшифровываю запись, пришлю результат.",
            reply_markup=_menu_keyboard(),
        )
    else:
        await state.set_state(GuidedFlow.awaiting_notebook)
        await message.answer(
            f"Задача #{job.id}: расшифровываю запись и размечаю роли. "
            "Когда пришлю «готово» — отправьте блокнот наблюдателя по этому упражнению (.xlsx) 📊",
            reply_markup=_menu_keyboard(),
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
        await state.clear()
        await message.answer("Не нашёл активное упражнение. Начните заново.", reply_markup=_menu_keyboard())
        return

    record = await session.scalar(
        select(InterviewRecord).where(InterviewRecord.exercise_id == exercise.id).order_by(InterviewRecord.id.desc())
    )
    if record is None:
        await message.answer(
            "⏳ Ещё расшифровываю аудио. Подождите сообщение «готово» и отправьте блокнот снова.",
            reply_markup=_menu_keyboard(),
        )
        return

    await message.answer("Получил блокнот наблюдателя. Сохраняю и обрабатываю...")
    try:
        local_path = await _download_notebook(bot, message)
        extract_notebook_indicators(local_path)
    except NotebookProcessingError as exc:
        await message.answer(
            f"Не удалось прочитать блокнот: {escape(str(exc), quote=False)}\n"
            "Проверьте файл и отправьте .xlsx ещё раз.",
            reply_markup=_menu_keyboard(),
        )
        return
    except Exception:
        logger.exception("Guided notebook upload failed")
        await message.answer(
            "Ошибка при загрузке блокнота (возможно, связь с Telegram). Отправьте файл .xlsx ещё раз.",
            reply_markup=_menu_keyboard(),
        )
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
        await message.answer("Не удалось обработать упражнение.", reply_markup=_retry_keyboard())
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
    await callback.message.answer("Готово.", reply_markup=_menu_keyboard())


@router.callback_query(F.data == "guided:home")
async def cb_home(callback: CallbackQuery, state: FSMContext) -> None:
    if callback.message is None:
        return
    await state.clear()
    await callback.answer()
    await callback.message.answer("🏠 Главное меню. Что сделать?", reply_markup=welcome_keyboard())


@router.callback_query(F.data == "guided:retry")
async def cb_retry(callback: CallbackQuery, session: AsyncSession, state: FSMContext) -> None:
    if callback.message is None:
        return
    data = await state.get_data()
    exercise_id = int(data["exercise_id"]) if data.get("exercise_id") else None
    exercise = await session.get(Exercise, exercise_id) if exercise_id else None
    if exercise is None:
        await callback.answer()
        await callback.message.answer("Повторять нечего. Вернёмся в меню.", reply_markup=welcome_keyboard())
        return

    record = await session.scalar(
        select(InterviewRecord).where(InterviewRecord.exercise_id == exercise.id).order_by(InterviewRecord.id.desc())
    )
    notebook = await session.scalar(
        select(ObserverNotebook).where(ObserverNotebook.exercise_id == exercise.id).order_by(ObserverNotebook.id.desc())
    )
    if record is None:
        await callback.answer()
        await callback.message.answer("⏳ Ещё расшифровываю аудио. Дождитесь сообщения «готово».", reply_markup=_menu_keyboard())
        return
    if notebook is None:
        await state.set_state(GuidedFlow.awaiting_notebook)
        await callback.answer()
        await callback.message.answer(
            "Отправьте блокнот наблюдателя по этому упражнению (.xlsx) 📊",
            reply_markup=_menu_keyboard(),
        )
        return

    await callback.answer("Повторяю обработку...")
    ok = await run_exercise_processing(callback.message, session, exercise)
    if ok:
        await callback.message.answer("✅ Готово. Что дальше?", reply_markup=_next_step_keyboard())
    else:
        await callback.message.answer("Снова не вышло.", reply_markup=_retry_keyboard())


async def on_guided_error(event: ErrorEvent) -> bool:
    """Last-resort safety net: on any unhandled error, give the user a way forward."""
    logger.exception("Guided flow error: %s", event.exception)
    update = event.update
    target: Message | None = update.message
    if target is None and update.callback_query is not None:
        target = update.callback_query.message
    if target is None:
        return True

    if isinstance(event.exception, TelegramNetworkError):
        text = (
            "⏳ Связь с Telegram сейчас подвисает — операция может занять чуть больше времени "
            "или повториться сама. Если файл не пришёл, попробуйте действие ещё раз чуть позже."
        )
        keyboard = _menu_keyboard()
    else:
        text = "⚠️ Что-то пошло не так. Можно попробовать ещё раз или вернуться в меню."
        keyboard = _retry_keyboard()
    try:
        await target.answer(text, reply_markup=keyboard)
    except Exception:
        logger.exception("Failed to send error fallback message")
    return True
