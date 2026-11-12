"""coverage_gap table

Revision ID: e7b9d1f3a5c4
Revises: d5a7c9e1b3f2
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "e7b9d1f3a5c4"
down_revision = "d5a7c9e1b3f2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "coverage_gap",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("absent_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=True),
        sa.Column("source", sa.String(20), nullable=False),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("status", sa.String(16), nullable=False, server_default="open"),
        sa.Column("open_shift_id", sa.Integer(), sa.ForeignKey("open_shift.id", ondelete="SET NULL"), nullable=True),
        sa.Column("filled_by_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("absent_user_id", "work_date", "source", name="uq_coverage_gap_absent_date_source"),
    )
    op.create_index("ix_coverage_gap_id", "coverage_gap", ["id"])
    op.create_index("ix_coverage_gap_shift_template_id", "coverage_gap", ["shift_template_id"])
    op.create_index("ix_coverage_gap_status_date", "coverage_gap", ["status", "work_date"])


def downgrade():
    op.drop_table("coverage_gap")
