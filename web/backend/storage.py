from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from bot.config import settings
from bot.models import (
    DevelopmentPlan,
    ExerciseTemplate,
    ExerciseTemplateMaterial,
    InterviewRecord,
    NotebookFillResult,
    ObserverNotebook,
    ParticipantReport,
)

logger = logging.getLogger(__name__)

# Files younger than this are never touched: an upload or a running transcription may
# have written them before its database row was committed.
MIN_AGE_MINUTES = 60


def _managed_dirs() -> list[Path]:
    """The only directories cleanup is ever allowed to look at."""
    uploads = settings.download_dir
    return [uploads, uploads.parent / "reports"]


async def _referenced_paths(session: AsyncSession) -> set[str]:
    """Every file path the database still points at."""
    columns = [
        InterviewRecord.file_path,
        ObserverNotebook.file_path,
        NotebookFillResult.output_path,
        ParticipantReport.output_path,
        DevelopmentPlan.output_path,
        ExerciseTemplate.notebook_path,
        ExerciseTemplateMaterial.file_path,
    ]
    referenced: set[str] = set()
    for column in columns:
        for value in await session.scalars(select(column)):
            if value:
                referenced.add(os.path.abspath(str(value)))
    return referenced


@dataclass
class OrphanFile:
    path: Path
    size: int
    age_hours: float


async def scan_orphans(session: AsyncSession) -> dict:
    """Find files on disk that nothing in the database points at. Never deletes."""
    referenced = await _referenced_paths(session)
    now = datetime.now(timezone.utc).timestamp()

    orphans: list[OrphanFile] = []
    total_files = 0
    total_size = 0
    skipped_recent = 0

    for directory in _managed_dirs():
        if not directory.is_dir():
            continue
        for entry in directory.iterdir():
            # Regular files only — no symlinks (they could point outside), no subdirs.
            if not entry.is_file() or entry.is_symlink():
                continue
            stat = entry.stat()
            total_files += 1
            total_size += stat.st_size
            if os.path.abspath(str(entry)) in referenced:
                continue
            age_hours = (now - stat.st_mtime) / 3600
            if age_hours * 60 < MIN_AGE_MINUTES:
                skipped_recent += 1
                continue
            orphans.append(OrphanFile(path=entry, size=stat.st_size, age_hours=age_hours))

    orphans.sort(key=lambda item: item.size, reverse=True)
    return {
        "total_files": total_files,
        "total_size": total_size,
        "orphan_count": len(orphans),
        "orphan_size": sum(item.size for item in orphans),
        "skipped_recent": skipped_recent,
        "min_age_minutes": MIN_AGE_MINUTES,
        "orphans": [
            {"name": item.path.name, "size": item.size, "age_hours": round(item.age_hours, 1)}
            for item in orphans[:200]
        ],
        "_paths": [item.path for item in orphans],
    }


async def delete_files_now_unreferenced(session: AsyncSession, paths: list[str]) -> dict:
    """Delete the given files, but only those nothing in the DB points at any more.

    Called right after an entity (centre/participant/exercise) is deleted, so its audio,
    filled notebooks and reports leave the disk immediately. The reference check makes it
    safe to pass a shared file (e.g. a catalog template's notebook): if another row still
    uses it, it is kept. Only files inside the managed dirs are ever touched.
    """
    if not paths:
        return {"deleted": 0, "freed": 0}

    referenced = await _referenced_paths(session)
    allowed = {d.resolve() for d in _managed_dirs()}

    deleted = 0
    freed = 0
    for raw in {os.path.abspath(p) for p in paths}:
        if raw in referenced:
            continue  # still used by another row — keep it
        path = Path(raw)
        try:
            if path.resolve().parent not in allowed or not path.is_file():
                continue
            size = path.stat().st_size
            path.unlink()
        except OSError:
            logger.warning("Could not delete file %s", path)
            continue
        deleted += 1
        freed += size
    return {"deleted": deleted, "freed": freed}


async def delete_orphans(session: AsyncSession) -> dict:
    """Delete exactly the files a fresh scan reports as orphaned."""
    scan = await scan_orphans(session)
    allowed = {d.resolve() for d in _managed_dirs()}

    deleted = 0
    freed = 0
    for path in scan["_paths"]:
        # Re-check containment right before unlinking, so nothing outside the managed
        # directories can ever be removed.
        if path.resolve().parent not in allowed:
            logger.warning("Refusing to delete file outside managed dirs: %s", path)
            continue
        try:
            size = path.stat().st_size
            path.unlink()
        except OSError:
            logger.warning("Could not delete orphan file %s", path)
            continue
        deleted += 1
        freed += size

    return {"deleted": deleted, "freed": freed}
