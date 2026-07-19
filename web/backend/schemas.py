from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CenterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=512)


class CenterOut(BaseModel):
    id: int
    name: str
    created_at: datetime | None = None
    participants: int = 0
    exercises: int = 0
    processed: int = 0


class ParticipantCreate(BaseModel):
    center_id: int
    # Privacy-safe identifier (no ФИО). Optional — omit to auto-assign a number.
    code: str | None = Field(default=None, max_length=512)


class ParticipantOut(BaseModel):
    id: int
    code: str
    center_id: int
    # Drives the download buttons: nothing to download until a report exists.
    has_report: bool = False
    processed_count: int = 0


class ExerciseCreate(BaseModel):
    center_id: int
    participant_id: int
    # Exercises are picked from the catalog — the name and materials come with it.
    template_id: int


class ExerciseOut(BaseModel):
    id: int
    name: str
    participant_id: int
    center_id: int
    has_instructions: bool = False
    template_id: int | None = None
    notebook_indicator_count: int | None = None
    has_result: bool = False
