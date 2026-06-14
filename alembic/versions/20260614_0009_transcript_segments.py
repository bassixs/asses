"""add transcript segments field

Revision ID: 20260614_0009
Revises: 20260606_0008
Create Date: 2026-06-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260614_0009"
down_revision = "20260606_0008"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("interview_records", sa.Column("transcript_segments", sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column("interview_records", "transcript_segments")
