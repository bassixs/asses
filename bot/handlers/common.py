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
        "Привет! Я помогу обработать упражнения ассессмент-центра: расшифровать аудио, "
        "заполнить блокнот наблюдателя, собрать отчет участника и ИПР.\n\n"
        "Быстрый сценарий для одной записи:\n"
        "1. Отправьте голосовое или аудиофайл.\n"
        "2. Я расшифрую запись и дам ее ID.\n"
        "3. Для простой оценки напишите /assess ID.\n\n"
        "Полный сценарий ассессмент-центра:\n"
        "1. Создайте центр: /create_center Название\n"
        "2. Добавьте участника: /add_participant ID_центра ФИО\n"
        "3. Добавьте упражнение: /add_exercise ID_участника Название упражнения\n"
        "4. Отправьте аудио упражнения и привяжите его: /attach_record ID_упражнения ID_записи\n"
        "5. Отправьте Excel-блокнот и привяжите его: /attach_notebook ID_упражнения ID_блокнота\n"
        "6. Запустите обработку: /process_exercise ID_упражнения\n"
        "7. После всех упражнений сформируйте отчет: /generate_report ID_участника\n"
        "8. Затем сформируйте ИПР: /generate_ipr ID_участника\n\n"
        "Что можно отправлять:\n"
        "• аудио/voice для расшифровки;\n"
        "• Excel .xlsx с блокнотом наблюдателя.\n\n"
        "Полезные команды:\n"
        "/centers — список центров\n"
        "/participants ID_центра — участники\n"
        "/exercises ID_участника — упражнения\n"
        "/criteria — критерии оценки\n"
        "/admin — админ-панель"
    )
    await message.answer(text, reply_markup=main_menu_keyboard())


@router.message(Command("criteria"))
async def cmd_criteria(message: Message) -> None:
    criteria = "\n".join(f"{idx}. {name}" for idx, name in enumerate(settings.competencies, start=1))
    await message.answer(f"Текущие критерии оценки:\n\n{criteria}", reply_markup=main_menu_keyboard())
