from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base

# Catalog states. An exercise is only selectable during assessment when it is
# "ready" (HR activated it after the AI confirmed understanding) AND a blank
# observer notebook is attached — see ExerciseTemplate.is_usable.
STATUS_DRAFT = "draft"
STATUS_READY = "ready"


class ExerciseTemplate(Base):
    """A pre-created exercise in the catalog.

    Materials (instructions/methodology) and the blank observer notebook are attached
    once, here — not per participant. The AI studies them and must confirm it
    understands the exercise before HR can activate it for use in assessments.
    """

    __tablename__ = "exercise_templates"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(512))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default=STATUS_DRAFT)

    # Concatenated text extracted from every attached material file.
    instructions_text: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Blank observer notebook (.xlsx) used for every assessment of this exercise.
    notebook_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    notebook_file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    notebook_indicator_count: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # The AI's structured understanding card + whether it confirmed full understanding.
    understanding_json: Mapped[dict[str, Any] | None] = mapped_column(JSON, nullable=True)
    understood: Mapped[bool] = mapped_column(Boolean, default=False)
    checked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    activated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    materials: Mapped[list["ExerciseTemplateMaterial"]] = relationship(
        back_populates="template",
        cascade="all, delete-orphan",
    )

    @property
    def is_usable(self) -> bool:
        """Selectable during assessment: activated by HR and has a blank notebook."""
        return self.status == STATUS_READY and bool(self.notebook_path)


class ExerciseTemplateMaterial(Base):
    """One uploaded material file of a catalog exercise (instructions / methodology)."""

    __tablename__ = "exercise_template_materials"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    template_id: Mapped[int] = mapped_column(
        ForeignKey("exercise_templates.id", ondelete="CASCADE"),
        index=True,
    )
    file_name: Mapped[str] = mapped_column(String(512))
    file_path: Mapped[str] = mapped_column(String(1024))
    chars: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    template: Mapped[ExerciseTemplate] = relationship(back_populates="materials")
