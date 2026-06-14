from __future__ import annotations

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, KeyboardButton, ReplyKeyboardMarkup


def main_menu_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="/centers"), KeyboardButton(text="/criteria")],
            [KeyboardButton(text="/my_assessments"), KeyboardButton(text="/admin")],
        ],
        resize_keyboard=True,
        input_field_placeholder="Отправьте аудио, Excel-блокнот или команду",
    )


def transcript_actions_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Оценить компетенции", callback_data=f"assess:{record_id}")],
            [InlineKeyboardButton(text="Скачать расшифровку", callback_data=f"transcript_file:{record_id}")],
        ]
    )


def stt_provider_keyboard(job_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="AI Tunnel Whisper", callback_data=f"stt_provider:{job_id}:aitunnel"),
                InlineKeyboardButton(text="Yandex", callback_data=f"stt_provider:{job_id}:yandex"),
            ],
            [InlineKeyboardButton(text="NeuroAPI Whisper", callback_data=f"stt_provider:{job_id}:neuroapi")],
        ]
    )


def report_format_keyboard(participant_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(text="PPTX", callback_data=f"report_format:{participant_id}:pptx"),
                InlineKeyboardButton(text="DOCX", callback_data=f"report_format:{participant_id}:docx"),
                InlineKeyboardButton(text="PDF", callback_data=f"report_format:{participant_id}:pdf"),
            ],
        ]
    )


def assessment_actions_keyboard(record_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="Повторить оценку", callback_data=f"assess:{record_id}")],
        ]
    )
