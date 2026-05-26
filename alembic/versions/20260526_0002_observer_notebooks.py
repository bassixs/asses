"""observer notebooks

Revision ID: 20260526_0002
Revises: 20260524_0001
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260526_0002"
down_revision = "20260524_0001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "observer_notebooks",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("file_id", sa.String(length=512), nullable=False),
        sa.Column("file_unique_id", sa.String(length=512), nullable=True),
        sa.Column("file_name", sa.String(length=512), nullable=True),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "notebook_fill_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "record_id",
            sa.Integer(),
            sa.ForeignKey("interview_records.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "notebook_id",
            sa.Integer(),
            sa.ForeignKey("observer_notebooks.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("output_path", sa.String(length=1024), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("notebook_fill_results")
    op.drop_table("observer_notebooks")
