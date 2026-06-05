"""add neuroapi stt provider fields

Revision ID: 20260605_0007
Revises: 20260604_0006
Create Date: 2026-06-05
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260605_0007"
down_revision = "20260604_0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("media_processing_jobs", sa.Column("stt_provider", sa.String(length=32), nullable=True))
    op.add_column("interview_records", sa.Column("stt_provider", sa.String(length=32), nullable=True))


def downgrade() -> None:
    op.drop_column("interview_records", "stt_provider")
    op.drop_column("media_processing_jobs", "stt_provider")
