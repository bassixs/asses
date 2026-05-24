from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/criteria"), KeyboardButton(text="/my_assessments")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Отправьте запись интервью или команду",
    )


def transcript_actions_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оценить компетенции", callback_data=f"assess:{record_id}")],
        ]
    )


def assessment_actions_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повторить оценку", callback_data=f"assess:{record_id}")],
        ]
    )

