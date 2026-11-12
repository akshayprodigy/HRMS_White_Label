"""rotation_pattern table

Revision ID: b7c8d9e0f1a3
Revises: f9a0b1c2d3e4
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "b7c8d9e0f1a3"
down_revision = "f9a0b1c2d3e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "rotation_pattern",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("cycle", sa.JSON(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_rotation_pattern_id", "rotation_pattern", ["id"])


def downgrade():
    op.drop_table("rotation_pattern")
