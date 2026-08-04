"""late-mark rules engine (W9)

Configurable late-mark rules + per-employee/month deduction tally that
cascades CL -> PL -> LOP, with the LOP portion feeding payroll.

Revision ID: r6s7t8u9v0w1
Revises: q5r6s7t8u9v0
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "r6s7t8u9v0w1"
down_revision = "q5r6s7t8u9v0"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "late_mark_rule",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("scope", sa.String(20), nullable=False, server_default="org_default"),
        sa.Column("shift_template_id", sa.Integer(), nullable=True),
        sa.Column("grace_minutes", sa.Integer(), nullable=False, server_default="10"),
        sa.Column("lates_per_deduction", sa.Integer(), nullable=False, server_default="3"),
        sa.Column("deduction_days_per_block", sa.Float(), nullable=False, server_default="1"),
        sa.Column("first_leave_type_id", sa.Integer(), nullable=True),
        sa.Column("second_leave_type_id", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now()),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.UniqueConstraint("name", name="uq_late_mark_rule_name"),
        sa.ForeignKeyConstraint(["shift_template_id"], ["shift_template.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_id"], ["user.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["first_leave_type_id"], ["leavetype.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["second_leave_type_id"], ["leavetype.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_late_mark_rule_scope", "late_mark_rule", ["scope"], unique=False)
    op.create_index("ix_late_mark_rule_shift_template_id", "late_mark_rule", ["shift_template_id"], unique=False)

    op.create_table(
        "late_mark_deduction",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), nullable=False),
        sa.Column("year", sa.Integer(), nullable=False),
        sa.Column("month", sa.Integer(), nullable=False),
        sa.Column("late_count", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("deducted_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("cl_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("pl_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("lop_days", sa.Float(), nullable=False, server_default="0"),
        sa.Column("payroll_run_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "year", "month", name="uq_late_mark_user_period"),
        sa.ForeignKeyConstraint(["user_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["payroll_run_id"], ["payrollrun.id"], ondelete="SET NULL"),
    )
    op.create_index("ix_late_mark_deduction_user_id", "late_mark_deduction", ["user_id"], unique=False)
    op.create_index("ix_late_mark_deduction_payroll_run_id", "late_mark_deduction", ["payroll_run_id"], unique=False)

    # Permission + grant to HR / Super Admin.
    op.execute(
        "INSERT INTO permission (name, description) VALUES "
        "('late mark rule write', 'Configure late-mark rules + process late-mark deductions') "
        "ON DUPLICATE KEY UPDATE description = VALUES(description);"
    )
    op.execute(
        """
        INSERT IGNORE INTO role_permissions (role_id, permission_id)
        SELECT r.id, p.id FROM role r, permission p
        WHERE r.name IN ('HR', 'Super Admin') AND p.name = 'late mark rule write';
        """
    )


def downgrade():
    op.execute(
        "DELETE rp FROM role_permissions rp JOIN permission p ON rp.permission_id = p.id "
        "WHERE p.name = 'late mark rule write';"
    )
    op.execute("DELETE FROM permission WHERE name = 'late mark rule write';")
    op.drop_index("ix_late_mark_deduction_payroll_run_id", table_name="late_mark_deduction")
    op.drop_index("ix_late_mark_deduction_user_id", table_name="late_mark_deduction")
    op.drop_table("late_mark_deduction")
    op.drop_index("ix_late_mark_rule_shift_template_id", table_name="late_mark_rule")
    op.drop_index("ix_late_mark_rule_scope", table_name="late_mark_rule")
    op.drop_table("late_mark_rule")
