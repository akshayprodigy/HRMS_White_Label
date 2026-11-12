"""coverage_requirement table

Revision ID: c3d4e5f6a7b8
Revises: b7c8d9e0f1a3
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "c3d4e5f6a7b8"
down_revision = "b7c8d9e0f1a3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coverage_requirement",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("min_headcount", sa.Integer(), nullable=False),
        sa.Column("max_headcount", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_coverage_requirement_id", "coverage_requirement", ["id"])
    op.create_index("ix_coverage_requirement_shift_template_id", "coverage_requirement", ["shift_template_id"])


def downgrade():
    op.drop_table("coverage_requirement")
