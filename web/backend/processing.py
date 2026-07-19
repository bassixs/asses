from __future__ import annotations

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import (
    AssessmentCenter,
    DevelopmentPlan,
    Exercise,
    InterviewRecord,
    NotebookFillResult,
    ObserverNotebook,
    Participant,
    ParticipantReport,
)
from bot.services.aitunnel_whisper import transcribe_aitunnel_with_segments
from bot.services.audio_chunking import merge_chunk_transcripts
from bot.services.audio_preprocessing import prepare_audio_chunks_for_upload
from bot.services.development_advice import enrich_competencies_with_advice
from bot.services.observer_notebook import (
    analyze_notebook_indicators,
    attach_evidence_timestamps,
    extract_notebook_indicators,
    fill_observer_notebook,
    read_filled_notebook,
    verify_evidence_quotes,
)
from bot.services.reports import (
    build_development_plan_text,
    build_participant_report_text,
    normalize_competence_name,
    save_development_plan_docx,
    save_participant_report_docx,
)
from bot.services.role_labeling import label_transcript_roles
from web.backend.deps import WEB_OWNER_ID

logger = logging.getLogger(__name__)

REPORTS_DIR = settings.download_dir.parent / "reports"


def _offset_segments(segments: list[dict[str, Any]], offset: float) -> list[dict[str, Any]]:
    if not offset:
        return segments
    return [{"start": float(seg["start"]) + offset, "text": seg["text"]} for seg in segments]


def _cleanup_derived(parts: list[tuple[Path, float]], original: Path) -> None:
    """Delete the temporary files chunking/compression produced, never the original.

    Anything whose path differs from the uploaded file is derived (a .chunkNNN piece or a
    compressed copy) and is useless once transcribed — otherwise these pile up forever.
    """
    for path, _ in parts:
        if path == original:
            continue
        try:
            path.unlink(missing_ok=True)
        except OSError:
            logger.warning("Could not delete temporary audio file %s", path)


async def transcribe_audio(audio_path: Path) -> tuple[str, list[dict[str, Any]]]:
    """Transcribe (with duration/size chunking) via AI Tunnel Whisper. Returns (text, segments)."""
    parts = await prepare_audio_chunks_for_upload(
        audio_path, max_bytes=settings.aitunnel_max_upload_bytes, provider_name="aitunnel"
    )
    try:
        if len(parts) == 1:
            path, offset = parts[0]
            text, segments = await transcribe_aitunnel_with_segments(path)
            return text, _offset_segments(segments, offset)

        transcripts: list[str] = []
        all_segments: list[dict[str, Any]] = []
        for path, offset in parts:
            text, segments = await transcribe_aitunnel_with_segments(path)
            transcripts.append(text)
            all_segments.extend(_offset_segments(segments, offset))
        return merge_chunk_transcripts(transcripts), all_segments
    finally:
        _cleanup_derived(parts, audio_path)


async def process_audio_exercise(session: AsyncSession, exercise_id: int) -> None:
    """Audio → transcript → role labeling → notebook analysis → filled notebook + result.

    Mirrors the bot's media_jobs + run_exercise_processing, without Telegram. Requires the
    exercise to already have an uploaded audio InterviewRecord (file_path) and an ObserverNotebook.
    """
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise ValueError("Упражнение не найдено")
    participant = await session.get(Participant, exercise.participant_id)

    record = await session.scalar(
        select(InterviewRecord)
        .where(InterviewRecord.exercise_id == exercise_id)
        .order_by(InterviewRecord.id.desc())
    )
    notebook = await session.scalar(
        select(ObserverNotebook)
        .where(ObserverNotebook.exercise_id == exercise_id)
        .order_by(ObserverNotebook.id.desc())
    )
    if record is None or not record.file_path:
        raise ValueError("Нет загруженного аудио для упражнения")
    if notebook is None:
        raise ValueError("Нет загруженного блокнота для упражнения")

    # 1) transcribe + role labeling (only if not done yet)
    if not record.transcript:
        raw_transcript, segments = await transcribe_audio(Path(record.file_path))
        transcript = await label_transcript_roles(
            raw_transcript,
            assessed_participant_name=participant.full_name if participant else None,
            exercise_name=exercise.name,
            exercise_instructions=exercise.instructions_text,
        )
        record.raw_transcript = raw_transcript
        record.transcript = transcript
        record.transcript_segments = json.dumps(segments, ensure_ascii=False)
        await session.commit()

    # 2) notebook analysis → fill → result_json
    input_path = Path(notebook.file_path)
    indicators = extract_notebook_indicators(input_path)
    report = await analyze_notebook_indicators(
        transcript=record.transcript,
        indicators=indicators,
        exercise_name=exercise.name,
        exercise_instructions=exercise.instructions_text,
    )
    verify_evidence_quotes(report, record.transcript)
    attach_evidence_timestamps(report, _load_segments(record.transcript_segments))

    output_path = REPORTS_DIR / f"exercise_{exercise_id}_filled.xlsx"
    result_json = fill_observer_notebook(
        input_path=input_path, output_path=output_path, indicators=indicators, report=report
    )
    await _store_fill_result(session, exercise_id, record.id, notebook.id, output_path, result_json)


async def store_filled_notebook(session: AsyncSession, exercise_id: int, notebook_path: Path) -> dict[str, Any]:
    """Read an HR-filled notebook as-is and store it as this exercise's result."""
    exercise = await session.get(Exercise, exercise_id)
    if exercise is None:
        raise ValueError("Упражнение не найдено")
    result_json = read_filled_notebook(notebook_path)

    notebook = ObserverNotebook(
        chat_id=WEB_OWNER_ID,
        user_id=WEB_OWNER_ID,
        exercise_id=exercise_id,
        file_id=f"web:{notebook_path.name}",
        file_name=notebook_path.name,
        file_path=str(notebook_path),
    )
    session.add(notebook)
    await session.commit()
    await session.refresh(notebook)
    await _store_fill_result(session, exercise_id, None, notebook.id, notebook_path, result_json)
    return result_json


async def _store_fill_result(
    session: AsyncSession,
    exercise_id: int,
    record_id: int | None,
    notebook_id: int,
    output_path: Path,
    result_json: dict[str, Any],
) -> None:
    fill = NotebookFillResult(
        exercise_id=exercise_id,
        record_id=record_id,
        notebook_id=notebook_id,
        chat_id=WEB_OWNER_ID,
        user_id=WEB_OWNER_ID,
        output_path=str(output_path),
        result_json=result_json,
    )
    session.add(fill)
    await session.commit()


def _load_segments(raw: str | None) -> list[dict[str, Any]]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return []
    return data if isinstance(data, list) else []


def _build_competency_matrix(fills: list[NotebookFillResult], exercise_by_id: dict[int, str]) -> dict[str, dict[str, Any]]:
    matrix: dict[str, dict[str, Any]] = {}
    for fill in fills:
        exercise_name = exercise_by_id.get(fill.exercise_id, f"Упражнение {fill.exercise_id}")
        levels = (fill.result_json or {}).get("levels", {}) or {}
        for competence, level_data in levels.items():
            level = level_data.get("level") if isinstance(level_data, dict) else level_data
            matrix.setdefault(normalize_competence_name(str(competence)), {})[exercise_name] = level
    return matrix


async def build_participant_report(session: AsyncSession, participant: Participant) -> ParticipantReport:
    """Aggregate all exercise results, enrich with LLM advice, persist a ParticipantReport."""
    fills = list(
        await session.scalars(
            select(NotebookFillResult)
            .join(Exercise, NotebookFillResult.exercise_id == Exercise.id)
            .where(Exercise.participant_id == participant.id)
            .order_by(NotebookFillResult.id)
        )
    )
    if not fills:
        raise ValueError("Нет обработанных упражнений для отчёта")

    _, result_json = build_participant_report_text(
        participant_name=participant.full_name,
        exercise_results=[item.result_json for item in fills],
    )
    await enrich_competencies_with_advice(
        result_json.get("competencies", {}), participant_name=participant.full_name
    )

    exercises = list(
        await session.scalars(
            select(Exercise).where(Exercise.participant_id == participant.id).order_by(Exercise.id)
        )
    )
    center = await session.get(AssessmentCenter, participant.center_id)
    exercise_by_id = {item.id: item.name for item in exercises}
    result_json["participant_name"] = participant.full_name
    result_json["center_name"] = center.name if center else None
    result_json["exercise_names"] = [item.name for item in exercises]
    result_json["matrix"] = _build_competency_matrix(fills, exercise_by_id)
    result_json["generated_date"] = datetime.now().strftime("%d.%m.%Y")

    report = ParticipantReport(
        participant_id=participant.id,
        chat_id=WEB_OWNER_ID,
        user_id=WEB_OWNER_ID,
        output_path="",
        result_json=result_json,
    )
    session.add(report)
    await session.commit()
    await session.refresh(report)
    return report


def render_report_file(participant_id: int, fmt: str, result_json: dict[str, Any]) -> Path:
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    name = result_json.get("participant_name") or ""
    center = result_json.get("center_name")
    exercise_names = result_json.get("exercise_names") or []

    if fmt == "docx":
        out = REPORTS_DIR / f"participant_{participant_id}_report.docx"
        save_participant_report_docx(
            path=out, participant_name=name, center_name=center,
            exercise_names=exercise_names, report_json=result_json,
        )
        return out

    from bot.services.report_pptx import save_participant_report_pptx

    out = REPORTS_DIR / f"participant_{participant_id}_report.pptx"
    save_participant_report_pptx(
        path=out, participant_name=name, center_name=center,
        exercise_names=exercise_names, report_json=result_json,
    )
    return out


async def build_ipr_file(session: AsyncSession, participant: Participant) -> Path:
    report = await session.scalar(
        select(ParticipantReport)
        .where(ParticipantReport.participant_id == participant.id)
        .order_by(ParticipantReport.id.desc())
    )
    if report is None:
        raise ValueError("Сначала сформируйте отчёт")

    _, plan_json = build_development_plan_text(
        participant_name=participant.full_name, report_json=report.result_json
    )
    center = await session.get(AssessmentCenter, participant.center_id)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = REPORTS_DIR / f"participant_{participant.id}_ipr.docx"
    save_development_plan_docx(
        path=output_path,
        participant_name=participant.full_name,
        center_name=center.name if center else None,
        plan_json=plan_json,
    )
    plan = DevelopmentPlan(
        participant_id=participant.id,
        chat_id=WEB_OWNER_ID,
        user_id=WEB_OWNER_ID,
        output_path=str(output_path),
        result_json=plan_json,
    )
    session.add(plan)
    await session.commit()
    return output_path
