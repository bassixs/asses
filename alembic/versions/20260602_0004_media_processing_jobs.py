"""media processing jobs

Revision ID: 20260602_0004
Revises: 20260526_0003
Create Date: 2026-06-02
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260602_0004"
down_revision = "20260526_0003"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interview_records", sa.Column("transcript_file_path", sa.String(length=1024), nullable=True))
    op.create_table(
        "media_processing_jobs",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("file_id", sa.String(length=512), nullable=False),
        sa.Column("file_unique_id", sa.String(length=512), nullable=True),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("file_name", sa.String(length=512), nullable=True),
        sa.Column("file_size", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, index=True),
        sa.Column(
            "record_id",
            sa.Integer(),
            sa.ForeignKey("interview_records.id", ondelete="SET NULL"),
            nullable=True,
            index=True,
        ),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("media_processing_jobs")
    op.drop_column("interview_records", "transcript_file_path")
