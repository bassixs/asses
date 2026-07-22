from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.models import Exercise, NotebookFillResult, Participant
from web.backend import jobs
from web.backend.deps import get_session
from web.backend.processing import build_ipr_file, build_participant_report, render_report_file

logger = logging.getLogger(__name__)
router = APIRouter(tags=["results"])

_XLSX_MIME = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_DOCX_MIME = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
_PPTX_MIME = "application/vnd.openxmlformats-officedocument.presentationml.presentation"


async def _latest_fill(exercise_id: int, session: AsyncSession) -> NotebookFillResult | None:
    return await session.scalar(
        select(NotebookFillResult)
        .where(NotebookFillResult.exercise_id == exercise_id)
        .order_by(NotebookFillResult.id.desc())
    )


@router.get("/exercises/{exercise_id}/status")
async def exercise_status(exercise_id: int, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Processing stage + whether a filled result exists (durable truth)."""
    fill = await _latest_fill(exercise_id, session)
    status = jobs.get_status(exercise_id)
    if fill is not None and status["stage"] not in {"processing"}:
        status = {"stage": "done", "message": "Готово"}

    data = (fill.result_json or {}) if fill else {}
    # Breakdown by indicator status, so the page can show what the assessment actually found
    # instead of just "готово".
    counts = {"+": 0, "-": 0, "НЗ": 0}
    for item in data.get("results") or []:
        raw = str((item or {}).get("status") or "").strip()
        key = "-" if raw in {"-", "−", "–"} else raw
        if key in counts:
            counts[key] += 1

    return {
        "stage": status["stage"],
        "message": status["message"],
        "has_result": fill is not None,
        "levels": data.get("levels", {}),
        "indicator_count": data.get("indicator_count"),
        "assessed_at": fill.created_at if fill else None,
        "source": "audio" if (fill and fill.record_id) else ("manual" if fill else None),
        "counts": counts if fill else None,
        "summary": data.get("participant_summary") or None,
    }


@router.get("/exercises/{exercise_id}/filled-notebook")
async def download_filled_notebook(exercise_id: int, session: AsyncSession = Depends(get_session)) -> FileResponse:
    fill = await _latest_fill(exercise_id, session)
    if fill is None or not fill.output_path or not Path(fill.output_path).exists():
        raise HTTPException(status_code=404, detail="Заполненный блокнот ещё не готов.")
    return FileResponse(fill.output_path, media_type=_XLSX_MIME, filename=Path(fill.output_path).name)


@router.post("/participants/{participant_id}/report")
async def build_report(participant_id: int, session: AsyncSession = Depends(get_session)) -> dict[str, object]:
    """Aggregate all exercises + LLM-personalise the report (slow). Persists a ParticipantReport."""
    participant = await session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    try:
        report = await build_participant_report(session, participant)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    competencies = report.result_json.get("competencies", {})
    return {
        "ok": True,
        "competencies": {
            name: {"avg_level": data.get("avg_level")} for name, data in competencies.items()
        },
    }


@router.get("/participants/{participant_id}/report/file")
async def download_report(
    participant_id: int,
    fmt: str = Query("docx", pattern="^(docx|pptx)$"),
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    from bot.models import ParticipantReport

    participant = await session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    report = await session.scalar(
        select(ParticipantReport)
        .where(ParticipantReport.participant_id == participant_id)
        .order_by(ParticipantReport.id.desc())
    )
    if report is None:
        raise HTTPException(status_code=400, detail="Сначала сформируйте отчёт (POST /report).")
    # DOCX/PPTX rendering is synchronous CPU work — off the loop so it doesn't freeze others.
    path = await asyncio.to_thread(render_report_file, participant_id, fmt, report.result_json)
    mime = _DOCX_MIME if fmt == "docx" else _PPTX_MIME
    return FileResponse(path, media_type=mime, filename=path.name)


@router.post("/participants/{participant_id}/ipr")
async def download_ipr(participant_id: int, session: AsyncSession = Depends(get_session)) -> FileResponse:
    participant = await session.get(Participant, participant_id)
    if participant is None:
        raise HTTPException(status_code=404, detail="Участник не найден")
    try:
        path = await build_ipr_file(session, participant)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return FileResponse(path, media_type=_DOCX_MIME, filename=path.name)
