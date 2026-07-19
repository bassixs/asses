from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, UploadFile
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import Exercise, ExerciseTemplate, ExerciseTemplateMaterial
from bot.models.exercise_template import STATUS_DRAFT, STATUS_READY
from bot.services.exercise_understanding import analyze_exercise_understanding
from bot.services.instruction_files import (
    InstructionExtractionError,
    append_instructions,
    extract_instruction_text,
    is_supported_instruction,
)
from bot.services.llm_json import LLMJSONError
from bot.services.observer_notebook import NotebookProcessingError, extract_notebook_indicators
from web.backend.deps import get_session

logger = logging.getLogger(__name__)
router = APIRouter(tags=["exercise-templates"])


class TemplateCreate(BaseModel):
    name: str
    description: str | None = None


async def _get_template(template_id: int, session: AsyncSession) -> ExerciseTemplate:
    template = await session.scalar(
        select(ExerciseTemplate)
        .where(ExerciseTemplate.id == template_id)
        .options(selectinload(ExerciseTemplate.materials))
    )
    if template is None:
        raise HTTPException(status_code=404, detail="Упражнение не найдено в каталоге")
    return template


def _out(template: ExerciseTemplate, *, full: bool = False) -> dict:
    data = {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "status": template.status,
        "understood": template.understood,
        "is_usable": template.is_usable,
        "has_notebook": bool(template.notebook_path),
        "notebook_file_name": template.notebook_file_name,
        "notebook_indicator_count": template.notebook_indicator_count,
        "material_count": len(template.materials),
        "instructions_chars": len(template.instructions_text or ""),
        "checked_at": template.checked_at,
        "activated_at": template.activated_at,
    }
    if full:
        data["understanding"] = template.understanding_json
        data["materials"] = [
            {"id": m.id, "file_name": m.file_name, "chars": m.chars} for m in template.materials
        ]
    return data


@router.get("/exercise-templates")
async def list_templates(
    usable_only: bool = False, session: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = await session.scalars(
        select(ExerciseTemplate)
        .options(selectinload(ExerciseTemplate.materials))
        .order_by(ExerciseTemplate.id.desc())
    )
    items = [t for t in rows]
    if usable_only:
        items = [t for t in items if t.is_usable]
    return [_out(t) for t in items]


@router.post("/exercise-templates")
async def create_template(
    payload: TemplateCreate, session: AsyncSession = Depends(get_session)
) -> dict:
    name = payload.name.strip()
    if not name:
        raise HTTPException(status_code=400, detail="Укажите название упражнения.")
    template = ExerciseTemplate(
        name=name,
        description=(payload.description or "").strip() or None,
        status=STATUS_DRAFT,
    )
    session.add(template)
    await session.commit()
    await session.refresh(template, ["materials"])
    return _out(template, full=True)


@router.get("/exercise-templates/{template_id}")
async def get_template(template_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    return _out(await _get_template(template_id, session), full=True)


@router.delete("/exercise-templates/{template_id}")
async def delete_template(template_id: int, session: AsyncSession = Depends(get_session)) -> dict:
    template = await _get_template(template_id, session)
    used = await session.scalar(
        select(Exercise.id).where(Exercise.template_id == template_id).limit(1)
    )
    if used is not None:
        raise HTTPException(
            status_code=400,
            detail="Упражнение уже использовалось в оценке — удалить нельзя.",
        )
    await session.delete(template)
    await session.commit()
    return {"ok": True}


async def _save_upload(upload: UploadFile, prefix: str) -> Path:
    settings.download_dir.mkdir(parents=True, exist_ok=True)
    suffix = Path(upload.filename or "").suffix or ".bin"
    dest = settings.download_dir / f"{prefix}_{uuid4().hex}{suffix}"
    with dest.open("wb") as handle:
        while chunk := await upload.read(1024 * 1024):
            handle.write(chunk)
    return dest


def _invalidate(template: ExerciseTemplate) -> None:
    """Materials changed → previous AI verdict no longer applies."""
    template.understood = False
    template.understanding_json = None
    template.checked_at = None
    template.status = STATUS_DRAFT
    template.activated_at = None


@router.post("/exercise-templates/{template_id}/materials")
async def upload_material(
    template_id: int, file: UploadFile, session: AsyncSession = Depends(get_session)
) -> dict:
    template = await _get_template(template_id, session)
    if not is_supported_instruction(file.filename):
        raise HTTPException(status_code=400, detail="Нужен файл PDF, DOCX, TXT или MD.")
    path = await _save_upload(file, "material")
    try:
        text = extract_instruction_text(path)
    except InstructionExtractionError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    template.instructions_text = append_instructions(
        template.instructions_text, text, source=file.filename
    )
    session.add(
        ExerciseTemplateMaterial(
            template_id=template.id,
            file_name=file.filename or path.name,
            file_path=str(path),
            chars=len(text),
        )
    )
    _invalidate(template)
    await session.commit()
    await session.refresh(template, ["materials"])
    return _out(template, full=True)


@router.post("/exercise-templates/{template_id}/notebook")
async def upload_notebook(
    template_id: int, file: UploadFile, session: AsyncSession = Depends(get_session)
) -> dict:
    """Attach the blank observer notebook used for every assessment of this exercise."""
    template = await _get_template(template_id, session)
    if not (file.filename or "").lower().endswith(".xlsx"):
        raise HTTPException(status_code=400, detail="Нужен блокнот в формате .xlsx.")
    path = await _save_upload(file, "template_notebook")
    try:
        indicators = extract_notebook_indicators(path)
    except NotebookProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    template.notebook_path = str(path)
    template.notebook_file_name = file.filename
    template.notebook_indicator_count = len(indicators)
    _invalidate(template)
    await session.commit()
    await session.refresh(template, ["materials"])
    return _out(template, full=True)


@router.post("/exercise-templates/{template_id}/check")
async def check_understanding(
    template_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Have the AI study the materials and report whether it understands the exercise."""
    template = await _get_template(template_id, session)
    if not template.notebook_path:
        raise HTTPException(
            status_code=400, detail="Сначала приложите пустой блокнот наблюдателя (.xlsx)."
        )
    if not (template.instructions_text or "").strip():
        raise HTTPException(
            status_code=400, detail="Сначала приложите материалы упражнения (инструкции/методичку)."
        )

    try:
        indicators = extract_notebook_indicators(Path(template.notebook_path))
    except NotebookProcessingError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    try:
        understanding = await analyze_exercise_understanding(
            name=template.name,
            description=template.description,
            instructions_text=template.instructions_text,
            indicators=indicators,
        )
    except LLMJSONError as exc:
        logger.exception("Understanding check failed for template %s", template_id)
        raise HTTPException(status_code=502, detail=f"ИИ не смог разобрать упражнение: {exc}") from exc

    template.understanding_json = understanding
    template.understood = bool(understanding.get("understood"))
    template.checked_at = datetime.now(timezone.utc)
    # A fresh verdict always returns the card to "not activated" — HR confirms explicitly.
    template.status = STATUS_DRAFT
    template.activated_at = None
    await session.commit()
    await session.refresh(template, ["materials"])
    return _out(template, full=True)


@router.post("/exercise-templates/{template_id}/activate")
async def activate_template(
    template_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """HR confirms the AI's understanding card and publishes the exercise to the catalog."""
    template = await _get_template(template_id, session)
    if not template.understood:
        raise HTTPException(
            status_code=400,
            detail="ИИ ещё не подтвердил полное понимание упражнения — активировать нельзя.",
        )
    template.status = STATUS_READY
    template.activated_at = datetime.now(timezone.utc)
    await session.commit()
    await session.refresh(template, ["materials"])
    return _out(template, full=True)


@router.post("/exercise-templates/{template_id}/deactivate")
async def deactivate_template(
    template_id: int, session: AsyncSession = Depends(get_session)
) -> dict:
    """Pull an exercise out of the catalog without touching its materials or verdict."""
    template = await _get_template(template_id, session)
    template.status = STATUS_DRAFT
    template.activated_at = None
    await session.commit()
    await session.refresh(template, ["materials"])
    return _out(template, full=True)
