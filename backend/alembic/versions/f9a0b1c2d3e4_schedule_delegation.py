"""schedule_delegation table

Revision ID: f9a0b1c2d3e4
Revises: d8e9f0a1b2c3
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "f9a0b1c2d3e4"
down_revision = "d8e9f0a1b2c3"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "schedule_delegation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("grantee_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("scope_type", sa.String(16), nullable=False),
        sa.Column("scope_value", sa.String(100), nullable=True),
        sa.Column("employee_ids", sa.JSON(), nullable=True),
        sa.Column("can_publish", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("can_approve_changes", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("valid_from", sa.Date(), nullable=False),
        sa.Column("valid_to", sa.Date(), nullable=True),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("granted_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_schedule_delegation_id", "schedule_delegation", ["id"])
    op.create_index("ix_schedule_delegation_grantee_id", "schedule_delegation", ["grantee_id"])


def downgrade():
    op.drop_table("schedule_delegation")
