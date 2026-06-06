"""add raw transcript field

Revision ID: 20260606_0008
Revises: 20260605_0007
Create Date: 2026-06-06
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260606_0008"
down_revision = "20260605_0007"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interview_records", sa.Column("raw_transcript", sa.Text(), nullable=True))
    op.execute("UPDATE interview_records SET raw_transcript = transcript WHERE raw_transcript IS NULL")


def downgrade() -> None:
    op.drop_column("interview_records", "raw_transcript")
