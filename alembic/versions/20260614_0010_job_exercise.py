"""add exercise_id to media jobs

Revision ID: 20260614_0010
Revises: 20260614_0009
Create Date: 2026-06-14
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260614_0010"
down_revision = "20260614_0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("media_processing_jobs") as batch:
        batch.add_column(sa.Column("exercise_id", sa.Integer(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("media_processing_jobs") as batch:
        batch.drop_column("exercise_id")
