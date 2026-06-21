"""add instructions_text to exercises

Revision ID: 20260622_0011
Revises: 20260614_0010
Create Date: 2026-06-22
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260622_0011"
down_revision = "20260614_0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("exercises") as batch:
        batch.add_column(sa.Column("instructions_text", sa.Text(), nullable=True))


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch:
        batch.drop_column("instructions_text")
