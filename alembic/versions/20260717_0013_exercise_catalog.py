"""exercise catalog: pre-created exercises with materials and AI understanding gate

Revision ID: 20260717_0013
Revises: 20260623_0012
Create Date: 2026-07-17
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260717_0013"
down_revision = "20260623_0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "exercise_templates",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("name", sa.String(length=512), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False, server_default="draft"),
        sa.Column("instructions_text", sa.Text(), nullable=True),
        sa.Column("notebook_path", sa.String(length=1024), nullable=True),
        sa.Column("notebook_file_name", sa.String(length=512), nullable=True),
        sa.Column("notebook_indicator_count", sa.Integer(), nullable=True),
        sa.Column("understanding_json", sa.JSON(), nullable=True),
        sa.Column("understood", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        "exercise_template_materials",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "template_id",
            sa.Integer(),
            sa.ForeignKey("exercise_templates.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("file_name", sa.String(length=512), nullable=False),
        sa.Column("file_path", sa.String(length=1024), nullable=False),
        sa.Column("chars", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_exercise_template_materials_template_id",
        "exercise_template_materials",
        ["template_id"],
    )

    with op.batch_alter_table("exercises") as batch:
        batch.add_column(sa.Column("template_id", sa.Integer(), nullable=True))
        batch.create_index("ix_exercises_template_id", ["template_id"])


def downgrade() -> None:
    with op.batch_alter_table("exercises") as batch:
        batch.drop_index("ix_exercises_template_id")
        batch.drop_column("template_id")

    op.drop_index("ix_exercise_template_materials_template_id", "exercise_template_materials")
    op.drop_table("exercise_template_materials")
    op.drop_table("exercise_templates")
