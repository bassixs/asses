from __future__ import annotations

import asyncio
import logging

from bot.database import async_session_maker
from web.backend.processing import process_audio_exercise

logger = logging.getLogger(__name__)

# In-memory processing status per exercise. Fine for a single-process uvicorn MVP; the DB
# records (InterviewRecord / NotebookFillResult) are the durable source of truth.
_STATUS: dict[int, dict[str, str]] = {}
# Hold references to running tasks so the event loop does not garbage-collect them.
_TASKS: set[asyncio.Task] = set()


def start_audio_processing(exercise_id: int) -> None:
    task = asyncio.create_task(run_audio_processing(exercise_id))
    _TASKS.add(task)
    task.add_done_callback(_TASKS.discard)


def get_status(exercise_id: int) -> dict[str, str]:
    return _STATUS.get(exercise_id, {"stage": "idle", "message": ""})


def _set(exercise_id: int, stage: str, message: str = "") -> None:
    _STATUS[exercise_id] = {"stage": stage, "message": message}


async def run_audio_processing(exercise_id: int) -> None:
    """Background task: transcribe + analyse the exercise, updating in-memory status."""
    _set(exercise_id, "processing", "Расшифровка и анализ...")
    try:
        async with async_session_maker() as session:
            await process_audio_exercise(session, exercise_id)
        _set(exercise_id, "done", "Готово")
    except Exception as exc:  # noqa: BLE001 - surface any failure as status
        logger.exception("Audio processing failed for exercise %s", exercise_id)
        _set(exercise_id, "error", str(exc))
