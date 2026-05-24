from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command
from aiogram.types import Message

from bot.config import settings
from bot.keyboards import main_menu_keyboard

router = Router()


@router.message(Command("start"))
async def cmd_start(message: Message) -> None:
    text = (
        "Привет! Я бот для HR-ассесмента управленческих компетенций.\n\n"
        "Отправьте голосовое сообщение, аудиофайл или документ с записью интервью. "
        "Я расшифрую запись и сохраню транскрипт.\n\n"
        "После расшифровки напишите /assess <ID> или нажмите кнопку оценки.\n"
        "Команды: /criteria, /my_assessments"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("criteria"))
async def cmd_criteria(message: Message) -> None:
    criteria = "\n".join(f"{idx}. {name}" for idx, name in enumerate(settings.competencies, start=1))
    await message.answer(f"Текущие критерии оценки:\n\n{criteria}", reply_markup=main_menu_keyboard())

