"""open_shift and open_shift_claim tables

Revision ID: a7c1d9e3f5b2
Revises: f6a7b8c9d0e2
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "a7c1d9e3f5b2"
down_revision = "f6a7b8c9d0e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "open_shift",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_template.id", ondelete="CASCADE"), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("location", sa.String(100), nullable=True),
        sa.Column("slots", sa.Integer(), nullable=False),
        sa.Column("filled", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("auto_confirm", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("excluded_user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_drop_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_open_shift_id", "open_shift", ["id"])
    op.create_index("ix_open_shift_work_date", "open_shift", ["work_date"])
    op.create_index("ix_open_shift_status_date", "open_shift", ["status", "work_date"])
    op.create_table(
        "open_shift_claim",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("open_shift_id", sa.Integer(), sa.ForeignKey("open_shift.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("open_shift_id", "user_id", name="uq_open_shift_claim_user"),
    )
    op.create_index("ix_open_shift_claim_id", "open_shift_claim", ["id"])
    op.create_index("ix_open_shift_claim_user_status", "open_shift_claim", ["user_id", "status"])


def downgrade():
    op.drop_table("open_shift_claim")
    op.drop_table("open_shift")
