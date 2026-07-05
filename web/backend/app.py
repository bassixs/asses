from __future__ import annotations

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from bot.database import init_db
from web.backend.routers import assessments, files, reports

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
