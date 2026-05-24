from __future__ import annotations

from html import escape
import logging
from typing import Any

from aiogram import F, Router
from aiogram.filters import Command
from aiogram.types import CallbackQuery, Message
from sqlalchemy import Select, desc, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from bot.keyboards import assessment_actions_keyboard
from bot.models import AssessmentResult, InterviewRecord
from bot.services.assessment import analyze_transcript
from bot.services.yandex_gpt import YandexGPTError

logger = logging.getLogger(__name__)
router = Router()

TELEGRAM_MESSAGE_LIMIT = 4096
SAFE_MESSAGE_LIMIT = 3800


def _format_assessment(result: dict[str, Any]) -> str:
    lines = ["📊 Оценка управленческих компетенций\n"]
    for item in result.get("competencies", []):
        status = "проявлена" if item.get("manifested") else "не проявлена"
        evidence = item.get("evidence") or []
        lines.append(f"• {escape(str(item.get('name')), quote=False)}: {item.get('score')}/5, {status}")
        lines.append(f"  Комментарий: {escape(str(item.get('comment')), quote=False)}")
        if evidence:
            quotes = "; ".join(f"«{escape(str(quote), quote=False)}»" for quote in evidence[:3])
            lines.append(f"  Цитаты: {quotes}")
        lines.append("")

    if result.get("overall_summary"):
        lines.append(f"Итог: {escape(str(result['overall_summary']), quote=False)}")
    if result.get("risks"):
        lines.append("\nРиски:")
        lines.extend(f"- {escape(str(risk), quote=False)}" for risk in result["risks"])
    if result.get("recommendations"):
        lines.append("\nЧто уточнить:")
        lines.extend(f"- {escape(str(rec), quote=False)}" for rec in result["recommendations"])

    return "\n".join(lines).strip()


def _split_message(text: str, limit: int = SAFE_MESSAGE_LIMIT) -> list[str]:
    if len(text) <= TELEGRAM_MESSAGE_LIMIT:
        return [text]

    chunks: list[str] = []
    current: list[str] = []
    current_len = 0
    for paragraph in text.split("\n\n"):
        paragraph_len = len(paragraph) + 2
        if current and current_len + paragraph_len > limit:
            chunks.append("\n\n".join(current))
            current = []
            current_len = 0
        if paragraph_len > limit:
            for start in range(0, len(paragraph), limit):
                chunks.append(paragraph[start : start + limit])
            continue
        current.append(paragraph)
        current_len += paragraph_len
    if current:
        chunks.append("\n\n".join(current))
    return chunks


def _parse_record_id(message: Message) -> int | None:
    command_args = (message.text or "").split(maxsplit=1)
    if len(command_args) == 2 and command_args[1].isdigit():
        return int(command_args[1])
    if message.reply_to_message and message.reply_to_message.text:
        for token in message.reply_to_message.text.replace(".", " ").split():
            if token.isdigit():
                return int(token)
    return None


async def _load_record(session: AsyncSession, record_id: int, user_id: int) -> InterviewRecord | None:
    stmt: Select[tuple[InterviewRecord]] = select(InterviewRecord).where(
        InterviewRecord.id == record_id,
        InterviewRecord.user_id == user_id,
    )
    return await session.scalar(stmt)


async def _run_assessment(
    *,
    record_id: int,
    user_id: int,
    chat_id: int,
    session: AsyncSession,
) -> tuple[AssessmentResult | None, str]:
    record = await _load_record(session, record_id, user_id)
    if record is None:
        return None, "Запись не найдена или принадлежит другому пользователю."

    try:
        result = await analyze_transcript(record.transcript)
    except YandexGPTError as exc:
        logger.exception("YandexGPT failed")
        return None, f"Не удалось выполнить оценку: {escape(str(exc), quote=False)}"
    except Exception:
        logger.exception("Unexpected assessment error")
        return None, "Произошла ошибка при оценке. Попробуйте позже."

    assessment = AssessmentResult(
        record_id=record.id,
        chat_id=chat_id,
        user_id=user_id,
        result_json=result,
        summary=result.get("overall_summary"),
    )
    session.add(assessment)
    await session.commit()
    await session.refresh(assessment)

    return assessment, _format_assessment(result)


@router.message(Command("assess"))
async def cmd_assess(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    record_id = _parse_record_id(message)
    if record_id is None:
        await message.answer("Укажите ID записи: /assess 123 или ответьте командой на сообщение с ID.")
        return

    await message.answer("Запускаю оценку компетенций. Это может занять пару минут...")
    assessment, text = await _run_assessment(
        record_id=record_id,
        user_id=message.from_user.id,
        chat_id=message.chat.id,
        session=session,
    )
    chunks = _split_message(text)
    for chunk in chunks[:-1]:
        await message.answer(chunk)
    await message.answer(
        chunks[-1],
        reply_markup=assessment_actions_keyboard(record_id) if assessment else None,
    )


@router.callback_query(F.data.startswith("assess:"))
async def callback_assess(callback: CallbackQuery, session: AsyncSession) -> None:
    if callback.from_user is None or callback.message is None:
        await callback.answer("Не удалось обработать запрос", show_alert=True)
        return

    record_id = int(callback.data.split(":", maxsplit=1)[1])
    await callback.answer("Оценка запущена")
    await callback.message.answer("Запускаю оценку компетенций. Это может занять пару минут...")
    assessment, text = await _run_assessment(
        record_id=record_id,
        user_id=callback.from_user.id,
        chat_id=callback.message.chat.id,
        session=session,
    )
    chunks = _split_message(text)
    for chunk in chunks[:-1]:
        await callback.message.answer(chunk)
    await callback.message.answer(
        chunks[-1],
        reply_markup=assessment_actions_keyboard(record_id) if assessment else None,
    )


@router.message(Command("my_assessments"))
async def cmd_my_assessments(message: Message, session: AsyncSession) -> None:
    if message.from_user is None:
        await message.answer("Не удалось определить пользователя.")
        return

    stmt = (
        select(AssessmentResult)
        .options(selectinload(AssessmentResult.record))
        .where(AssessmentResult.user_id == message.from_user.id)
        .order_by(desc(AssessmentResult.created_at))
        .limit(20)
    )
    assessments = list(await session.scalars(stmt))
    if not assessments:
        await message.answer("Пока нет проведённых оценок. Отправьте запись интервью и затем /assess <ID>.")
        return

    lines = ["Ваши последние оценки:"]
    for assessment in assessments:
        created_at = assessment.created_at.strftime("%Y-%m-%d %H:%M")
        lines.append(
            f"• Оценка #{assessment.id}, запись #{assessment.record_id}, {created_at}: "
            f"{escape(assessment.summary or 'без краткого вывода', quote=False)}"
        )

    await message.answer("\n".join(lines))
