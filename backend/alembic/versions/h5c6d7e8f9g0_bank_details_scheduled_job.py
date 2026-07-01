"""add bank detail columns to employee + scheduled_job table

Pure additive — nullable columns on existing tables, new table for
the scheduled-job registry. Existing rows untouched, no data migration.

Revision ID: h5c6d7e8f9g0
Revises: g4b5c6d7e8f9
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "h5c6d7e8f9g0"
down_revision = "g4b5c6d7e8f9"
branch_labels = None
depends_on = None


def upgrade():
    # ---- Employee bank detail columns (all nullable) ------------
    op.add_column(
        "employee",
        sa.Column("bank_ifsc_code", sa.String(11), nullable=True),
    )
    op.add_column(
        "employee",
        sa.Column(
            "bank_account_holder_name", sa.String(120), nullable=True,
        ),
    )
    op.add_column(
        "employee",
        sa.Column(
            "bank_verified_at", sa.DateTime(timezone=True), nullable=True,
        ),
    )
    op.add_column(
        "employee",
        sa.Column("bank_verified_by_id", sa.Integer(), nullable=True),
    )
    op.create_foreign_key(
        "fk_employee_bank_verified_by",
        "employee", "user",
        ["bank_verified_by_id"], ["id"],
        ondelete="SET NULL",
    )

    # ---- scheduled_job registry ---------------------------------
    op.create_table(
        "scheduled_job",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("display_name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("cadence_cron", sa.String(80), nullable=False),
        sa.Column("enabled", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("is_running", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("last_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_status", sa.String(16),
                  nullable=False, server_default="idle"),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("last_summary", sa.Text(), nullable=True),
        sa.Column("last_duration_ms", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_scheduled_job_name"),
    )
    op.create_index(
        "ix_scheduled_job_enabled", "scheduled_job", ["enabled"]
    )


def downgrade():
    op.drop_index("ix_scheduled_job_enabled", table_name="scheduled_job")
    op.drop_table("scheduled_job")

    op.drop_constraint(
        "fk_employee_bank_verified_by", "employee", type_="foreignkey"
    )
    op.drop_column("employee", "bank_verified_by_id")
    op.drop_column("employee", "bank_verified_at")
    op.drop_column("employee", "bank_account_holder_name")
    op.drop_column("employee", "bank_ifsc_code")
