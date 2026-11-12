"""approval SLA escalation columns + approver_delegation

Revision ID: 013b7dbef090
Revises: d6f8a1c3e5b7
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "013b7dbef090"
down_revision = "d6f8a1c3e5b7"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("approvalstep", sa.Column(
        "escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("approvalstep", sa.Column(
        "escalated_from_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_apprstep_escalated_from", "approvalstep", "user",
        ["escalated_from_id"], ["id"], ondelete="SET NULL")
    op.add_column("chained_approval_step_instance", sa.Column(
        "due_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chained_approval_step_instance", sa.Column(
        "escalated_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("chained_approval_step_instance", sa.Column(
        "escalated_from_id", sa.Integer(), nullable=True))
    op.create_foreign_key(
        "fk_chainstep_escalated_from", "chained_approval_step_instance",
        "user", ["escalated_from_id"], ["id"], ondelete="SET NULL")
    op.create_table(
        "approver_delegation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey(
            "user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("delegate_id", sa.Integer(), sa.ForeignKey(
            "user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("starts_on", sa.Date(), nullable=False),
        sa.Column("ends_on", sa.Date(), nullable=True),
        sa.Column("only_when_on_leave", sa.Boolean(), nullable=False,
                  server_default="0"),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_approver_delegation_id", "approver_delegation", ["id"])
    op.create_index("ix_approver_delegation_user_id",
                    "approver_delegation", ["user_id"])
    op.create_index("ix_approver_delegation_delegate",
                    "approver_delegation", ["delegate_id", "revoked_at"])


def downgrade():
    op.drop_table("approver_delegation")
    op.drop_constraint("fk_chainstep_escalated_from",
                       "chained_approval_step_instance", type_="foreignkey")
    for c in ("escalated_from_id", "escalated_at", "due_at"):
        op.drop_column("chained_approval_step_instance", c)
    op.drop_constraint("fk_apprstep_escalated_from", "approvalstep",
                       type_="foreignkey")
    op.drop_column("approvalstep", "escalated_from_id")
    op.drop_column("approvalstep", "escalated_at")
