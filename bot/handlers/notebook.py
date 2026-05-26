from __future__ import annotations

from html import escape
import logging
import re
from pathlib import Path

from aiogram import Bot, F, Router
from aiogram.filters import Command
from aiogram.types import FSInputFile, Message
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import InterviewRecord, NotebookFillResult, ObserverNotebook
from bot.services.observer_notebook import (
    NotebookProcessingError,
    analyze_notebook_indicators,
    extract_notebook_indicators,
    fill_observer_notebook,
)

logger = logging.getLogger(__name__)
router = Router()

_SAFE_FILE_NAME_RE = re.compile(r"[^A-Za-z0-9_.-]+")


def _is_excel_document(message: Message) -> bool:
    if not message.document:
        return False
    file_name = message.document.file_name or ""
    return file_name.lower().endswith(".xlsx")


async def _download_notebook(bot: Bot, message: Message) -> Path:
    if not message.document:
        raise ValueError("Message has no document")

    tg_file = await bot.get_file(message.document.file_id)
    if tg_file.file_path is None:
        raise RuntimeError("Telegram did not return file_path")

    settings.download_dir.mkdir(parents=True, exist_ok=True)
    safe_name = _SAFE_FILE_NAME_RE.sub("_", message.document.file_name or message.document.file_id)
    destination = settings.download_dir / f"notebook_{message.document.file_unique_id}_{safe_name}"
    await bot.download_file(tg_file.file_path, destination=destination)
    return destination


def _parse_fill_args(message: Message) -> tuple[int, int] | None:
    parts = (message.text or "").split()
    if len(parts) != 3:
        return None
    if not parts[1].isdigit() or not parts[2].isdigit():
        return None
    return int(parts[1]), int(parts[2])


@router.message(F.document, _is_excel_document)
async def handle_observer_notebook(message: Message, bot: Bot, session: AsyncSession) -> None:
    if message.from_user is None or message.document is None:
        await message.answer("Не удалось определить пользователя или файл.")
        return

    await message.answer("Получил Excel-блокнот наблюдателя. Сохраняю структуру...")
    try:
        local_path = await _download_notebook(bot, message)
        indicators = extract_notebook_indicators(local_path)
    except NotebookProcessingError as exc:
        logger.exception("Invalid observer notebook")
        await message.answer(f"Не удалось прочитать блокнот: {escape(str(exc), quote=False)}")
        return
    except Exception:
        logger.exception("Unexpected notebook upload error")
        await message.answer("Произошла ошибка при загрузке блокнота. Проверьте, что это .xlsx файл.")
        return

    notebook = ObserverNotebook(
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        file_id=message.document.file_id,
        file_unique_id=message.document.file_unique_id,
        file_name=message.document.file_name,
        file_path=str(local_path),
    )
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)

    await message.answer(
        "✅ Блокнот наблюдателя загружен.\n"
        f"ID блокнота: {notebook.id}\n"
        f"Найдено индикаторов: {len(indicators)}\n\n"
        f"После расшифровки аудио запустите: /fill_notebook <ID записи> {notebook.id}"
    )


@router.message(Command("fill_notebook"))
async def cmd_fill_notebook(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    parsed = _parse_fill_args(message)
    if parsed is None:
        await message.answer("Укажите ID записи и ID блокнота: /fill_notebook 123 45")
        return

    record_id, notebook_id = parsed
    record = await session.scalar(
        select(InterviewRecord).where(
            InterviewRecord.id == record_id,
            InterviewRecord.user_id == message.from_user.id,
        )
    )
    notebook = await session.scalar(
        select(ObserverNotebook).where(
            ObserverNotebook.id == notebook_id,
            ObserverNotebook.user_id == message.from_user.id,
        )
    )

    if record is None:
        await message.answer("Запись не найдена или принадлежит другому пользователю.")
        return
    if notebook is None:
        await message.answer("Блокнот не найден или принадлежит другому пользователю.")
        return

    await message.answer("Заполняю блокнот наблюдателя. Это может занять несколько минут...")
    try:
        input_path = Path(notebook.file_path)
        indicators = extract_notebook_indicators(input_path)
        report = await analyze_notebook_indicators(transcript=record.transcript, indicators=indicators)
        output_path = settings.download_dir.parent / "reports" / f"filled_record_{record.id}_notebook_{notebook.id}.xlsx"
        result_json = fill_observer_notebook(
            input_path=input_path,
            output_path=output_path,
            indicators=indicators,
            report=report,
        )
    except NotebookProcessingError as exc:
        logger.exception("Notebook processing failed")
        await message.answer(f"Не удалось заполнить блокнот: {escape(str(exc), quote=False)}")
        return
    except Exception:
        logger.exception("Unexpected notebook filling error")
        await message.answer("Произошла ошибка при заполнении блокнота. Подробности записаны в лог.")
        return

    fill_result = NotebookFillResult(
        record_id=record.id,
        notebook_id=notebook.id,
        chat_id=message.chat.id,
        user_id=message.from_user.id,
        output_path=str(output_path),
        result_json=result_json,
    )
    session.add(fill_result)
    await session.commit()

    await message.answer_document(
        FSInputFile(output_path),
        caption=_format_fill_summary(record.id, notebook.id, result_json),
    )


def _format_fill_summary(record_id: int, notebook_id: int, result_json: dict[str, object]) -> str:
    levels = result_json.get("levels", {})
    lines = [
        f"✅ Заполнен блокнот #{notebook_id} по записи #{record_id}.",
        f"Индикаторов обработано: {result_json.get('indicator_count', 0)}",
        "",
        "Уровни компетенций:",
    ]
    if isinstance(levels, dict):
        for competence, data in levels.items():
            if isinstance(data, dict):
                lines.append(
                    f"• {competence}: {data.get('level')} "
                    f"({data.get('plus_count')}/{data.get('observed_count')}, {data.get('percent')}%)"
                )
    return "\n".join(lines)
