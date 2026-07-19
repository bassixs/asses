from __future__ import annotations

import base64
import logging
import secrets
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response

from bot.config import settings
from bot.database import init_db
from web.backend.routers import assessments, files, overview, reports, templates
from web.backend.seed import seed_builtin_templates

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

@app.middleware("http")
async def basic_auth(request: Request, call_next):
    """Protect the whole site with HTTP Basic (any user, password = ADMIN_BOT_PASSWORD).

    Disabled when the password is empty. The browser prompts once and reuses the header.
    """
    password = settings.admin_bot_password
    if not password:
        return await call_next(request)
    header = request.headers.get("authorization", "")
    authorized = False
    if header.startswith("Basic "):
        try:
            _, _, supplied = base64.b64decode(header[6:]).decode("utf-8").partition(":")
            authorized = secrets.compare_digest(supplied, password)
        except Exception:  # noqa: BLE001 - malformed header → unauthorized
            authorized = False
    if not authorized:
        return Response(status_code=401, headers={"WWW-Authenticate": 'Basic realm="Assessment"'})
    return await call_next(request)


app.include_router(assessments.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(overview.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(templates.router, prefix="/api")


@app.on_event("startup")
async def _on_startup() -> None:
    await init_db()
    await seed_builtin_templates()


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
