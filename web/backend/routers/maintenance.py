from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from web.backend.deps import get_session
from web.backend.storage import delete_orphans, scan_orphans

router = APIRouter(tags=["maintenance"])


@router.get("/storage")
async def storage(session: AsyncSession = Depends(get_session)) -> dict:
    """Disk usage and the list of files nothing points at (read-only)."""
    result = await scan_orphans(session)
    result.pop("_paths", None)
    return result


@router.post("/storage/cleanup")
async def storage_cleanup(session: AsyncSession = Depends(get_session)) -> dict:
    """Delete orphaned files. Only files a fresh scan reports as unreferenced."""
    return {"ok": True, **(await delete_orphans(session))}
