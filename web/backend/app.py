from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse

from bot.database import init_db
from web.backend.routers import assessments, files, reports

_DIST = Path(__file__).resolve().parent.parent / "frontend" / "dist"

logging.basicConfig(level=logging.INFO)

app = FastAPI(title="HR Assessment Center", version="0.1.0")

# Dev: the SPA runs on a different port. Tighten allow_origins for production.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(assessments.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(reports.router, prefix="/api")


@app.on_event("startup")
async def _on_startup() -> None:
    await init_db()


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}


# Serve the built SPA (web/frontend/dist) when present, with client-side-routing fallback.
# In dev the frontend runs via Vite, dist is absent, and only /api is served here.
if _DIST.exists():

    @app.get("/{full_path:path}")
    async def spa(full_path: str) -> FileResponse:
        if full_path.startswith("api/"):
            raise HTTPException(status_code=404)
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
