from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from sqlalchemy import BigInteger, DateTime, ForeignKey, JSON, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class ObserverNotebook(Base):
    __tablename__ = "observer_notebooks"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercises.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    file_id: Mapped[str] = mapped_column(String(512))
    file_unique_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_name: Mapped[str | None] = mapped_column(String(512), nullable=True)
    file_path: Mapped[str] = mapped_column(String(1024))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    fills: Mapped[list["NotebookFillResult"]] = relationship(
        back_populates="notebook",
        cascade="all, delete-orphan",
    )


class NotebookFillResult(Base):
    __tablename__ = "notebook_fill_results"

    id: Mapped[int] = mapped_column(primary_key=True, autoincrement=True)
    exercise_id: Mapped[int | None] = mapped_column(
        ForeignKey("exercises.id", ondelete="SET NULL"),
        index=True,
        nullable=True,
    )
    record_id: Mapped[int] = mapped_column(
        ForeignKey("interview_records.id", ondelete="CASCADE"),
        index=True,
    )
    notebook_id: Mapped[int] = mapped_column(
        ForeignKey("observer_notebooks.id", ondelete="CASCADE"),
        index=True,
    )
    chat_id: Mapped[int] = mapped_column(BigInteger, index=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    output_path: Mapped[str] = mapped_column(String(1024))
    result_json: Mapped[dict[str, Any]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    notebook: Mapped[ObserverNotebook] = relationship(back_populates="fills")
