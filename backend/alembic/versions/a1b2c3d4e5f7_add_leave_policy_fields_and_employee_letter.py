"""Add leave policy fields and employee letter table

Revision ID: a1b2c3d4e5f7
Revises: f2a3b4c5d6e7
Create Date: 2026-03-25

"""

from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f7"
down_revision = "f2a3b4c5d6e7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # -- LeaveType policy fields --
    op.add_column("leavetype", sa.Column("code", sa.String(10), nullable=True))
    op.add_column("leavetype", sa.Column("annual_quota", sa.Float(), nullable=True))
    op.add_column("leavetype", sa.Column("max_carry_forward", sa.Float(), nullable=True))
    op.add_column("leavetype", sa.Column("max_accumulation", sa.Float(), nullable=True))
    op.add_column("leavetype", sa.Column("max_consecutive_days", sa.Integer(), nullable=True))
    op.add_column("leavetype", sa.Column("allow_half_day", sa.Boolean(), server_default=sa.text("1"), nullable=False))
    op.add_column("leavetype", sa.Column("requires_medical_cert_after", sa.Integer(), nullable=True))
    op.add_column("leavetype", sa.Column("is_cumulative", sa.Boolean(), server_default=sa.text("1"), nullable=False))
    op.add_column("leavetype", sa.Column("use_within_days", sa.Integer(), nullable=True))
    op.add_column("leavetype", sa.Column("max_per_month", sa.Integer(), nullable=True))
    op.add_column("leavetype", sa.Column("max_per_year", sa.Integer(), nullable=True))
    op.create_index("ix_leavetype_code", "leavetype", ["code"], unique=True)

    # -- EmployeeLetter table --
    op.create_table(
        "employeeletter",
        sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("letter_type", sa.String(50), nullable=False, index=True),
        sa.Column("reference_number", sa.String(50), nullable=True, unique=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("generated_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("template_data", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20), server_default="draft"),
    )


def downgrade() -> None:
    op.drop_table("employeeletter")
    op.drop_index("ix_leavetype_code", table_name="leavetype")
    op.drop_column("leavetype", "max_per_year")
    op.drop_column("leavetype", "max_per_month")
    op.drop_column("leavetype", "use_within_days")
    op.drop_column("leavetype", "is_cumulative")
    op.drop_column("leavetype", "requires_medical_cert_after")
    op.drop_column("leavetype", "allow_half_day")
    op.drop_column("leavetype", "max_consecutive_days")
    op.drop_column("leavetype", "max_accumulation")
    op.drop_column("leavetype", "max_carry_forward")
    op.drop_column("leavetype", "annual_quota")
    op.drop_column("leavetype", "code")
