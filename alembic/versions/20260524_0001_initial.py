"""initial schema

Revision ID: 20260524_0001
Revises:
Create Date: 2026-05-24
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260524_0001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "interview_records",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("file_id", sa.String(length=512), nullable=False),
        sa.Column("file_unique_id", sa.String(length=512), nullable=True),
        sa.Column("file_type", sa.String(length=32), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=True),
        sa.Column("transcript", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "assessment_results",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "record_id",
            sa.Integer(),
            sa.ForeignKey("interview_records.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("assessment_results")
    op.drop_table("interview_records")

