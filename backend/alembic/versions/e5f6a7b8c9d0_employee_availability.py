"""employee_availability table

Revision ID: e5f6a7b8c9d0
Revises: d4e5f6a7b8c9
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "e5f6a7b8c9d0"
down_revision = "d4e5f6a7b8c9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "employee_availability",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=True),
        sa.Column("specific_date", sa.Date(), nullable=True),
        sa.Column("shift_template_id", sa.Integer(), sa.ForeignKey("shift_template.id", ondelete="CASCADE"), nullable=True),
        sa.Column("valid_from", sa.Date(), nullable=True),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_employee_availability_id", "employee_availability", ["id"])
    op.create_index("ix_employee_availability_user_id", "employee_availability", ["user_id"])


def downgrade():
    op.drop_table("employee_availability")
