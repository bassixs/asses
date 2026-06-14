from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from aiogram.fsm.context import FSMContext

from bot.config import settings
from bot.keyboards import welcome_keyboard

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message, state: FSMContext) -> None:
    await state.clear()
    text = (
        "👋 Привет! Я помогаю обрабатывать упражнения ассессмент-центра:\n"
        "расшифровываю аудио, заполняю блокнот наблюдателя, собираю отчёт участника и ИПР.\n\n"
        "Выберите, что нужно сделать — дальше я буду вести по шагам и подсказывать, "
        "что отправить (кнопки ниже).\n\n"
        "📝 Расшифровать запись — просто получить текст из аудио.\n"
        "📊 Оценить одно упражнение — провести один полный цикл.\n"
        "🏆 Оценить все упражнения — несколько упражнений одного участника → общий отчёт и ИПР.\n\n"
        "Опытные пользователи могут работать командами (/create_center, /process_exercise и т.д.)."
    )
    await message.answer(text, reply_markup=welcome_keyboard())


@router.message(Command("criteria"))
async def cmd_criteria(message: Message) -> None:
    criteria = "\n".join(f"{idx}. {name}" for idx, name in enumerate(settings.competencies, start=1))
    await message.answer(f"Текущие критерии оценки:\n\n{criteria}")
