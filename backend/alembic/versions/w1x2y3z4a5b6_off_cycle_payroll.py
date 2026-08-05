"""off-cycle payroll run (W5)

Adds run_type / scope_user_ids / reason / created_by to payrollrun so a run
can be scoped to specific employees (off-cycle) instead of the whole active
roster. Monthly runs keep scope_user_ids NULL and behave exactly as before.

Revision ID: w1x2y3z4a5b6
Revises: v0w1x2y3z4a5
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "w1x2y3z4a5b6"
down_revision = "v0w1x2y3z4a5"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("payrollrun", sa.Column("run_type", sa.String(20), nullable=False, server_default="monthly"))
    op.add_column("payrollrun", sa.Column("scope_user_ids", sa.JSON(), nullable=True))
    op.add_column("payrollrun", sa.Column("reason", sa.String(500), nullable=True))
    op.add_column("payrollrun", sa.Column("created_by_id", sa.Integer(), nullable=True))
    op.create_index("ix_payrollrun_run_type", "payrollrun", ["run_type"], unique=False)
    op.create_foreign_key("fk_payrollrun_created_by", "payrollrun", "user", ["created_by_id"], ["id"])


def downgrade():
    op.drop_constraint("fk_payrollrun_created_by", "payrollrun", type_="foreignkey")
    op.drop_index("ix_payrollrun_run_type", table_name="payrollrun")
    op.drop_column("payrollrun", "created_by_id")
    op.drop_column("payrollrun", "reason")
    op.drop_column("payrollrun", "scope_user_ids")
    op.drop_column("payrollrun", "run_type")
