from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from bot.models.base import Base


class InterviewRecord(Base):
    __tablename__ = "interview_records"

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
    file_type: Mapped[str] = mapped_column(String(32))
    file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    transcript_file_path: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    transcript: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )

    assessments: Mapped[list["AssessmentResult"]] = relationship(
        back_populates="record",
        cascade="all, delete-orphan",
    )
