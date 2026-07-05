"""make notebook_fill_results.record_id nullable

Revision ID: 20260623_0012
Revises: 20260622_0011
Create Date: 2026-06-23
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260623_0012"
down_revision = "20260622_0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("notebook_fill_results") as batch:
        batch.alter_column("record_id", existing_type=sa.Integer(), nullable=True)


def downgrade() -> None:
    with op.batch_alter_table("notebook_fill_results") as batch:
        batch.alter_column("record_id", existing_type=sa.Integer(), nullable=False)
