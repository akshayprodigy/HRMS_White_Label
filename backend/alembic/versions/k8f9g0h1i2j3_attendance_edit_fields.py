"""add HR edit-trail columns to attendance

Section Q: HR/admin can directly edit punch-in/punch-out times (and
create records for fully-missed days). Edited rows carry a permanent
marker so the UI can badge them; the who/what/why detail lives in the
audit log.

- edited_by_id : user who last hand-edited the record (nullable FK)
- edited_at    : when the last hand-edit happened (nullable)

Revision ID: k8f9g0h1i2j3
Revises: j7e8f9g0h1i2
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa


revision = "k8f9g0h1i2j3"
down_revision = "j7e8f9g0h1i2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column(
        "attendance",
        sa.Column("edited_by_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "attendance",
        sa.Column("edited_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_foreign_key(
        "fk_attendance_edited_by_id_user",
        "attendance",
        "user",
        ["edited_by_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade():
    op.drop_constraint(
        "fk_attendance_edited_by_id_user", "attendance", type_="foreignkey"
    )
    op.drop_column("attendance", "edited_at")
    op.drop_column("attendance", "edited_by_id")
