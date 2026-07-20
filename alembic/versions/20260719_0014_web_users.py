"""web users: multiple sign-in accounts over a shared workspace

Revision ID: 20260719_0014
Revises: 20260717_0013
Create Date: 2026-07-19
"""
from __future__ import annotations

from alembic import op
import sqlalchemy as sa

revision = "20260719_0014"
down_revision = "20260717_0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "web_users",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("username", sa.String(length=128), nullable=False),
        sa.Column("password_hash", sa.String(length=256), nullable=False),
        sa.Column("is_admin", sa.Boolean(), nullable=False, server_default=sa.text("0")),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_login", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_web_users_username", "web_users", ["username"], unique=True)


def downgrade() -> None:
    op.drop_index("ix_web_users_username", "web_users")
    op.drop_table("web_users")
