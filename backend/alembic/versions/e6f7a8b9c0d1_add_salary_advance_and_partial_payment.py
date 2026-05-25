"""add salary advance and partial payment

Revision ID: e6f7a8b9c0d1
Revises: d5e6f7a8b9c0
Create Date: 2026-03-27

"""
from alembic import op
import sqlalchemy as sa

revision = "e6f7a8b9c0d1"
down_revision = "d5e6f7a8b9c0"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Salary Advance table
    op.create_table(
        "salaryadvance",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("disbursed_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "recovery_mode", sa.String(20), nullable=False, server_default="one_time"
        ),
        sa.Column(
            "installment_months", sa.Integer(), nullable=False, server_default="1"
        ),
        sa.Column(
            "recovered_amount", sa.Float(), nullable=False, server_default="0"
        ),
        sa.Column(
            "status", sa.String(20), nullable=False, server_default="active", index=True
        ),
        sa.Column("approved_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=False),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
    )

    # Advance Recovery table
    op.create_table(
        "advancerecovery",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column(
            "advance_id",
            sa.Integer(),
            sa.ForeignKey("salaryadvance.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column(
            "payroll_run_id",
            sa.Integer(),
            sa.ForeignKey("payrollrun.id"),
            nullable=True,
        ),
        sa.Column("amount", sa.Float(), nullable=False),
        sa.Column(
            "recovered_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
        ),
        sa.Column("remarks", sa.String(255), nullable=True),
    )

    # Add partial payment columns to payrollline
    op.add_column(
        "payrollline",
        sa.Column("advance_deduction", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "payrollline",
        sa.Column("disbursed_amount", sa.Float(), nullable=True),
    )
    op.add_column(
        "payrollline",
        sa.Column("held_amount", sa.Float(), server_default="0", nullable=False),
    )
    op.add_column(
        "payrollline",
        sa.Column("held_reason", sa.String(255), nullable=True),
    )
    op.add_column(
        "payrollline",
        sa.Column(
            "held_released", sa.Boolean(), server_default=sa.text("0"), nullable=False
        ),
    )
    op.add_column(
        "payrollline",
        sa.Column(
            "held_released_in_run_id",
            sa.Integer(),
            sa.ForeignKey("payrollrun.id"),
            nullable=True,
        ),
    )


def downgrade() -> None:
    op.drop_column("payrollline", "held_released_in_run_id")
    op.drop_column("payrollline", "held_released")
    op.drop_column("payrollline", "held_reason")
    op.drop_column("payrollline", "held_amount")
    op.drop_column("payrollline", "disbursed_amount")
    op.drop_column("payrollline", "advance_deduction")
    op.drop_table("advancerecovery")
    op.drop_table("salaryadvance")
