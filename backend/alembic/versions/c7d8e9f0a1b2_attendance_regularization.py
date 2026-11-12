"""attendance regularization requests

Revision ID: c7d8e9f0a1b2
Revises: b6c7d8e9f0a1
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "c7d8e9f0a1b2"
down_revision = "b6c7d8e9f0a1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "attendance_regularization",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("attendance_id", sa.Integer(), nullable=True),
        sa.Column("requested_punch_in", sa.DateTime(timezone=True), nullable=False),
        sa.Column("requested_punch_out", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["attendance_id"], ["attendance.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["user.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_attendance_regularization_id", "attendance_regularization", ["id"])
    op.create_index("ix_attendance_regularization_user_id", "attendance_regularization", ["user_id"])
    op.create_index("ix_attendance_regularization_work_date", "attendance_regularization", ["work_date"])
    op.create_index("ix_attendance_regularization_status", "attendance_regularization", ["status"])


def downgrade():
    op.drop_table("attendance_regularization")
