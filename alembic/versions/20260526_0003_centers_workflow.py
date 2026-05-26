"""assessment center workflow

Revision ID: 20260526_0003
Revises: 20260526_0002
Create Date: 2026-05-26
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260526_0003"
down_revision = "20260526_0002"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "assessment_centers",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "participants",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "center_id",
            sa.Integer(),
            sa.ForeignKey("assessment_centers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("full_name", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "exercises",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "center_id",
            sa.Integer(),
            sa.ForeignKey("assessment_centers.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "participant_reports",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("output_path", sa.String(length=1024), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "development_plans",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "participant_id",
            sa.Integer(),
            sa.ForeignKey("participants.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("chat_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("user_id", sa.BigInteger(), nullable=False, index=True),
        sa.Column("output_path", sa.String(length=1024), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("interview_records", sa.Column("exercise_id", sa.Integer(), nullable=True))
    op.create_index("ix_interview_records_exercise_id", "interview_records", ["exercise_id"])
    op.add_column("observer_notebooks", sa.Column("exercise_id", sa.Integer(), nullable=True))
    op.create_index("ix_observer_notebooks_exercise_id", "observer_notebooks", ["exercise_id"])
    op.add_column("notebook_fill_results", sa.Column("exercise_id", sa.Integer(), nullable=True))
    op.create_index("ix_notebook_fill_results_exercise_id", "notebook_fill_results", ["exercise_id"])


def downgrade() -> None:
    op.drop_index("ix_notebook_fill_results_exercise_id", table_name="notebook_fill_results")
    op.drop_column("notebook_fill_results", "exercise_id")
    op.drop_index("ix_observer_notebooks_exercise_id", table_name="observer_notebooks")
    op.drop_column("observer_notebooks", "exercise_id")
    op.drop_index("ix_interview_records_exercise_id", table_name="interview_records")
    op.drop_column("interview_records", "exercise_id")
    op.drop_table("development_plans")
    op.drop_table("participant_reports")
    op.drop_table("exercises")
    op.drop_table("participants")
    op.drop_table("assessment_centers")
