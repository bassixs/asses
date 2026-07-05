from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CenterCreate(BaseModel):
    name: str = Field(min_length=1, max_length=512)


class CenterOut(BaseModel):
    id: int
    name: str
    created_at: datetime | None = None


class ParticipantCreate(BaseModel):
    center_id: int
    # Privacy-safe identifier (no ФИО). Optional — omit to auto-assign a number.
    code: str | None = Field(default=None, max_length=512)


class ParticipantOut(BaseModel):
    id: int
    code: str
    center_id: int


class ExerciseCreate(BaseModel):
    center_id: int
    participant_id: int
    name: str = Field(min_length=1, max_length=512)


class ExerciseOut(BaseModel):
    id: int
    name: str
    participant_id: int
    center_id: int
    has_instructions: bool = False
