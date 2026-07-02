"""shift change requests (Section R)

Employee-initiated shift change with Manager -> HR approval via the
generic chain engine. On approval the chain endpoint materializes the
EmployeeShiftAssignment.

Revision ID: l9g0h1i2j3k4
Revises: k8f9g0h1i2j3
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa


revision = "l9g0h1i2j3k4"
down_revision = "k8f9g0h1i2j3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shift_change_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False, index=True,
        ),
        sa.Column(
            "current_shift_template_id", sa.Integer(),
            sa.ForeignKey("shift_template.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "requested_shift_template_id", sa.Integer(),
            sa.ForeignKey("shift_template.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default="pending", index=True,
        ),
        sa.Column(
            "approval_instance_id", sa.Integer(),
            sa.ForeignKey(
                "chained_approval_instance.id", ondelete="SET NULL"
            ),
            nullable=True, index=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True), nullable=False,
        ),
        sa.Column(
            "decided_at", sa.DateTime(timezone=True), nullable=True,
        ),
    )


def downgrade():
    op.drop_table("shift_change_request")
