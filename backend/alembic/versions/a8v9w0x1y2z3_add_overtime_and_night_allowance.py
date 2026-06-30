"""add overtime + night-shift allowance rules and entries

Step 4 of the 24x7 shift engine.

Adds:
- overtime_rule                  : OT policy master (org/shift scoped)
- night_shift_allowance_rule     : Night-shift allowance master
- overtime_entry                 : per-attendance computed OT, approval-routed
- night_allowance_entry          : per-attendance night allowance

Backward compatibility
----------------------
No existing rows are touched. With zero rules configured, the
compute/inject paths produce zero entries and zero payroll line items.

Revision ID: a8v9w0x1y2z3
Revises: z7u8v9w0x1y2
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "a8v9w0x1y2z3"
down_revision = "z7u8v9w0x1y2"
branch_labels = None
depends_on = None


def upgrade():
    # ----- overtime_rule -------------------------------------------------
    op.create_table(
        "overtime_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "scope",
            sa.String(20),
            nullable=False,
            server_default="org_default",
        ),
        sa.Column(
            "shift_template_id",
            sa.Integer(),
            sa.ForeignKey("shift_template.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "ot_basis",
            sa.String(30),
            nullable=False,
            server_default="beyond_shift_hours",
        ),
        sa.Column("daily_threshold_hours", sa.Float(), nullable=True),
        sa.Column(
            "ot_rate_multiplier",
            sa.Float(),
            nullable=False,
            server_default=sa.text("1.5"),
        ),
        sa.Column(
            "weekly_off_multiplier",
            sa.Float(),
            nullable=False,
            server_default=sa.text("2.0"),
        ),
        sa.Column(
            "holiday_multiplier",
            sa.Float(),
            nullable=False,
            server_default=sa.text("2.0"),
        ),
        sa.Column(
            "min_ot_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "daily_ot_cap_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("240"),
        ),
        sa.Column("monthly_ot_cap_minutes", sa.Integer(), nullable=True),
        sa.Column(
            "rounding_minutes",
            sa.Integer(),
            nullable=False,
            server_default=sa.text("30"),
        ),
        sa.Column(
            "requires_approval",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("name", name="uq_overtime_rule_name"),
    )
    op.create_index(
        "ix_overtime_rule_scope", "overtime_rule", ["scope"]
    )
    op.create_index(
        "ix_overtime_rule_shift", "overtime_rule", ["shift_template_id"]
    )

    # ----- night_shift_allowance_rule -----------------------------------
    op.create_table(
        "night_shift_allowance_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column(
            "scope",
            sa.String(20),
            nullable=False,
            server_default="org_default",
        ),
        sa.Column(
            "shift_template_id",
            sa.Integer(),
            sa.ForeignKey("shift_template.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column(
            "payout_model",
            sa.String(20),
            nullable=False,
            server_default="flat",
        ),
        sa.Column(
            "flat_amount", sa.Float(), nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "hourly_rate", sa.Float(), nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column("night_window_start", sa.Time(), nullable=False),
        sa.Column("night_window_end", sa.Time(), nullable=False),
        sa.Column(
            "min_night_minutes", sa.Integer(),
            nullable=False, server_default=sa.text("60"),
        ),
        sa.Column(
            "is_active", sa.Boolean(),
            nullable=False, server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("name", name="uq_night_rule_name"),
    )
    op.create_index(
        "ix_night_rule_scope", "night_shift_allowance_rule", ["scope"]
    )
    op.create_index(
        "ix_night_rule_shift",
        "night_shift_allowance_rule",
        ["shift_template_id"],
    )

    # ----- overtime_entry ----------------------------------------------
    op.create_table(
        "overtime_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column(
            "attendance_id", sa.Integer(),
            sa.ForeignKey("attendance.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "shift_template_id", sa.Integer(),
            sa.ForeignKey("shift_template.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "rule_id", sa.Integer(),
            sa.ForeignKey("overtime_rule.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "ot_minutes", sa.Integer(), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "ot_amount", sa.Float(), nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "hourly_rate_used", sa.Float(), nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "multiplier_used", sa.Float(), nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "day_type", sa.String(20), nullable=False,
            server_default="weekday",
        ),
        sa.Column(
            "status", sa.String(20), nullable=False,
            server_default="pending",
        ),
        sa.Column(
            "approver_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "approval_item_id", sa.Integer(),
            sa.ForeignKey("approvalitem.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.String(500), nullable=True),
        sa.Column(
            "payroll_run_id", sa.Integer(),
            sa.ForeignKey("payrollrun.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "work_date", name="uq_ot_user_workdate"
        ),
    )
    op.create_index("ix_ot_entry_user", "overtime_entry", ["user_id"])
    op.create_index("ix_ot_entry_workdate", "overtime_entry", ["work_date"])
    op.create_index("ix_ot_entry_status", "overtime_entry", ["status"])
    op.create_index("ix_ot_entry_run", "overtime_entry", ["payroll_run_id"])

    # ----- night_allowance_entry ---------------------------------------
    op.create_table(
        "night_allowance_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "user_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column(
            "attendance_id", sa.Integer(),
            sa.ForeignKey("attendance.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "rule_id", sa.Integer(),
            sa.ForeignKey(
                "night_shift_allowance_rule.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column(
            "night_minutes", sa.Integer(), nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column(
            "amount", sa.Float(), nullable=False,
            server_default=sa.text("0.0"),
        ),
        sa.Column(
            "payout_model_used", sa.String(20), nullable=False,
            server_default="flat",
        ),
        sa.Column(
            "payroll_run_id", sa.Integer(),
            sa.ForeignKey("payrollrun.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "user_id", "work_date", name="uq_night_user_workdate"
        ),
    )
    op.create_index("ix_night_entry_user", "night_allowance_entry", ["user_id"])
    op.create_index("ix_night_entry_workdate", "night_allowance_entry", ["work_date"])
    op.create_index("ix_night_entry_run", "night_allowance_entry", ["payroll_run_id"])


def downgrade():
    op.drop_index("ix_night_entry_run", table_name="night_allowance_entry")
    op.drop_index("ix_night_entry_workdate", table_name="night_allowance_entry")
    op.drop_index("ix_night_entry_user", table_name="night_allowance_entry")
    op.drop_table("night_allowance_entry")

    op.drop_index("ix_ot_entry_run", table_name="overtime_entry")
    op.drop_index("ix_ot_entry_status", table_name="overtime_entry")
    op.drop_index("ix_ot_entry_workdate", table_name="overtime_entry")
    op.drop_index("ix_ot_entry_user", table_name="overtime_entry")
    op.drop_table("overtime_entry")

    op.drop_index("ix_night_rule_shift", table_name="night_shift_allowance_rule")
    op.drop_index("ix_night_rule_scope", table_name="night_shift_allowance_rule")
    op.drop_table("night_shift_allowance_rule")

    op.drop_index("ix_overtime_rule_shift", table_name="overtime_rule")
    op.drop_index("ix_overtime_rule_scope", table_name="overtime_rule")
    op.drop_table("overtime_rule")
