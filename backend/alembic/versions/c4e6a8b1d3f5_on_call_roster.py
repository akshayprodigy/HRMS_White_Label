"""on-call roster + shift allowance entries

Revision ID: c4e6a8b1d3f5
Revises: b3d5f7a9c2e4
Create Date: 2026-11-13
"""
from alembic import op
import sqlalchemy as sa

revision = "c4e6a8b1d3f5"
down_revision = "b3d5f7a9c2e4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "on_call_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False, unique=True),
        sa.Column("payout_model", sa.String(20), nullable=False),
        sa.Column("flat_amount", sa.Float(), nullable=False),
        sa.Column("hourly_rate", sa.Float(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_on_call_rule_id", "on_call_rule", ["id"])
    op.create_table(
        "on_call_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("is_overnight", sa.Boolean(), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("on_call_rule.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "work_date", name="uq_on_call_user_date"),
    )
    op.create_index("ix_on_call_assignment_id", "on_call_assignment", ["id"])
    op.create_index("ix_on_call_assignment_user_id", "on_call_assignment", ["user_id"])
    op.create_index("ix_on_call_assignment_work_date", "on_call_assignment", ["work_date"])
    op.create_table(
        "shift_allowance_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("minutes", sa.Integer(), nullable=False),
        sa.Column("rule_id", sa.Integer(), sa.ForeignKey("on_call_rule.id", ondelete="SET NULL"), nullable=True),
        sa.Column("source_id", sa.Integer(), nullable=True),
        sa.Column("payroll_run_id", sa.Integer(), sa.ForeignKey("payrollrun.id", ondelete="SET NULL"), nullable=True),
        sa.Column("computed_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("user_id", "work_date", "kind", name="uq_shift_allow_user_date_kind"),
    )
    op.create_index("ix_shift_allowance_entry_id", "shift_allowance_entry", ["id"])
    op.create_index("ix_shift_allowance_entry_user_id", "shift_allowance_entry", ["user_id"])
    op.create_index("ix_shift_allowance_entry_work_date", "shift_allowance_entry", ["work_date"])
    op.create_index("ix_shift_allowance_entry_payroll_run_id", "shift_allowance_entry", ["payroll_run_id"])


def downgrade():
    op.drop_table("shift_allowance_entry")
    op.drop_table("on_call_assignment")
    op.drop_table("on_call_rule")
