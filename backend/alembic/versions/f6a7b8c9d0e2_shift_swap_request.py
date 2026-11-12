"""shift_swap_request table

Revision ID: f6a7b8c9d0e2
Revises: e5f6a7b8c9d0
Create Date: 2026-11-12
"""
from alembic import op
import sqlalchemy as sa

revision = "f6a7b8c9d0e2"
down_revision = "e5f6a7b8c9d0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shift_swap_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("requester_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("counterparty_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("requester_date", sa.Date(), nullable=False),
        sa.Column("counterparty_date", sa.Date(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("snapshot", sa.JSON(), nullable=True),
        sa.Column("peer_responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decided_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_shift_swap_request_id", "shift_swap_request", ["id"])
    op.create_index("ix_shift_swap_cp_status", "shift_swap_request", ["counterparty_id", "status"])
    op.create_index("ix_shift_swap_req_status", "shift_swap_request", ["requester_id", "status"])


def downgrade():
    op.drop_table("shift_swap_request")
