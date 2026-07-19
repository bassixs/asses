from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse

from bot.database import init_db
from web.backend.auth import COOKIE_NAME, auth_required, verify_token
from web.backend.routers import (
    assessments,
    auth,
    files,
    maintenance,
    overview,
    reports,
    templates,
)
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

# Endpoints reachable without a session: signing in, checking whether we are signed in,
# and the health probe. Everything else under /api needs a valid session cookie.
_PUBLIC_API = {"/api/auth/login", "/api/auth/logout", "/api/auth/me", "/api/health"}


@app.middleware("http")
async def session_auth(request: Request, call_next):
    """Gate the API behind a signed session cookie.

    The SPA shell (HTML/JS/CSS) is served publicly so the sign-in page can load; it
    carries no data of its own. Every endpoint that returns or changes data is protected.
    Disabled entirely when no password is configured.
    """
    path = request.url.path
    if not auth_required() or not path.startswith("/api/") or path in _PUBLIC_API:
        return await call_next(request)

    if verify_token(request.cookies.get(COOKIE_NAME)):
        return await call_next(request)
    return JSONResponse({"detail": "Не выполнен вход"}, status_code=401)


app.include_router(auth.router, prefix="/api")
app.include_router(assessments.router, prefix="/api")
app.include_router(files.router, prefix="/api")
app.include_router(maintenance.router, prefix="/api")
app.include_router(overview.router, prefix="/api")
app.include_router(reports.router, prefix="/api")
app.include_router(templates.router, prefix="/api")


@app.on_event("startup")
async def _on_startup() -> None:
    await init_db()
    try:
        await seed_builtin_templates()
    except Exception:  # noqa: BLE001 - seeding is a convenience, never a reason to refuse to boot
        logging.exception("Could not seed built-in exercise templates; continuing without them")


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
