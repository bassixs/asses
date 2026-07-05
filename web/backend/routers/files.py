from __future__ import annotations

import logging
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import Exercise, InterviewRecord, ObserverNotebook
from bot.services.instruction_files import (
    InstructionExtractionError,
    append_instructions,
    extract_instruction_text,
    is_supported_instruction,
)
from bot.services.observer_notebook import NotebookProcessingError, extract_notebook_indicators
from web.backend import jobs
from web.backend.deps import WEB_OWNER_ID, get_session
from web.backend.processing import store_filled_notebook

logger = logging.getLogger(__name__)
router = APIRouter(tags=["files"])


async def _save_upload(upload: UploadFile, prefix: str) -> Path:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix or ".bin"
    dest = settings.download_dir / f"{prefix}_{uuid4().hex}{suffix}"
    with dest.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            handle.write(chunk)
    return dest


async def _get_exercise(exercise_id: int, session: AsyncSession) -> Exercise:
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено")
    return exercise


@router.post("/exercises/{exercise_id}/instructions")
async def upload_instructions(
    exercise_id: int, file: UploadFile, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    exercise = await _get_exercise(exercise_id, session)
    if not is_supported_instruction(file.filename):
        raise HTTPException(status_code=400, detail="Нужен файл инструкции PDF или DOCX.")
    path = await _save_upload(file, "instruction")
    try:
        text = extract_instruction_text(path)
    except InstructionExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    exercise.instructions_text = append_instructions(exercise.instructions_text, text, source=file.filename)
    await session.commit()
    return {"ok": True, "chars": len(exercise.instructions_text or "")}


@router.post("/exercises/{exercise_id}/notebook")
async def upload_notebook_template(
    exercise_id: int, file: UploadFile, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    """Upload the (empty) observer notebook that the AI will fill from the audio."""
    await _get_exercise(exercise_id, session)
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Нужен блокнот в формате .xlsx.")
    path = await _save_upload(file, "notebook")
    try:
        indicators = extract_notebook_indicators(path)
    except NotebookProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    notebook = ObserverNotebook(
        chat_id=WEB_OWNER_ID,
        user_id=WEB_OWNER_ID,
        exercise_id=exercise_id,
        file_id=f"web:{path.name}",
        file_name=file.filename,
        file_path=str(path),
    )
    session.add(notebook)
    await session.commit()
    return {"ok": True, "indicators": len(indicators)}


@router.post("/exercises/{exercise_id}/audio")
async def upload_audio(
    exercise_id: int, file: UploadFile, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    """Upload audio and start background transcription + analysis (notebook must be uploaded first)."""
    await _get_exercise(exercise_id, session)
    if not settings.aitunnel_api_key:
        raise HTTPException(status_code=503, detail="AI Tunnel API key не настроен.")
    notebook = await session.scalar(
        select(ObserverNotebook).where(ObserverNotebook.exercise_id == exercise_id)
    )
    if notebook is None:
        raise HTTPException(status_code=400, detail="Сначала загрузите блокнот наблюдателя (.xlsx).")

    path = await _save_upload(file, "audio")
    record = InterviewRecord(
        chat_id=WEB_OWNER_ID,
        user_id=WEB_OWNER_ID,
        exercise_id=exercise_id,
        file_id=f"web:{path.name}",
        file_type="audio",
        file_path=str(path),
        stt_provider="aitunnel",
        transcript="",
    )
    session.add(record)
    await session.commit()

    jobs.start_audio_processing(exercise_id)
    return {"ok": True, "status": "processing"}


@router.post("/exercises/{exercise_id}/filled-notebook")
async def upload_filled_notebook(
    exercise_id: int, file: UploadFile, session: AsyncSession = Depends(get_session)
) -> dict[str, object]:
    """Upload an already-filled observer notebook; read scores as-is (no audio, no AI)."""
    await _get_exercise(exercise_id, session)
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Нужен заполненный блокнот в формате .xlsx.")
    path = await _save_upload(file, "filled_notebook")
    try:
        result_json = await store_filled_notebook(session, exercise_id, path)
    except NotebookProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "ok": True,
        "indicators": result_json.get("indicator_count"),
        "levels": result_json.get("levels", {}),
    }
