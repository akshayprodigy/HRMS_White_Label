"""projects profitability

Revision ID: 0009_projects_profitability
Revises: 0008_projects_dpr
Create Date: 2026-02-06

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0009_projects_profitability"
down_revision = "0008_projects_dpr"
branch_labels = None
depends_on = None

_FK_EMPLOYEES_ID = "employees.id"
_FK_PROJECTS_ID = "projects.id"


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column(
            "created_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
            server_onupdate=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("created_by", sa.BigInteger(), nullable=True),
        sa.Column("updated_by", sa.BigInteger(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        "attendance_entries",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "employee_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_EMPLOYEES_ID),
            nullable=False,
        ),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_PROJECTS_ID),
            nullable=False,
        ),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("hours", sa.Numeric(8, 2), nullable=False),
        sa.Column("hourly_rate", sa.Numeric(14, 2), nullable=False),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *_audit_columns(),
    )
    op.create_index(
        "ix_attendance_entries_project_id_work_date",
        "attendance_entries",
        ["project_id", "work_date"],
    )
    op.create_index(
        "ix_attendance_entries_employee_id_work_date",
        "attendance_entries",
        ["employee_id", "work_date"],
    )

    op.create_table(
        "project_direct_expenses",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_PROJECTS_ID),
            nullable=False,
        ),
        sa.Column("expense_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("vendor", sa.String(length=255), nullable=True),
        sa.Column("reference_no", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *_audit_columns(),
    )
    op.create_index(
        "ix_project_direct_expenses_project_id",
        "project_direct_expenses",
        ["project_id"],
    )
    op.create_index(
        "ix_project_direct_expenses_expense_date",
        "project_direct_expenses",
        ["expense_date"],
    )
    op.create_index(
        "ix_project_direct_expenses_project_id_expense_date",
        "project_direct_expenses",
        ["project_id", "expense_date"],
    )

    op.create_table(
        "project_revenues",
        sa.Column(
            "id",
            sa.BigInteger(),
            primary_key=True,
            autoincrement=True,
        ),
        sa.Column(
            "project_id",
            sa.BigInteger(),
            sa.ForeignKey(_FK_PROJECTS_ID),
            nullable=False,
        ),
        sa.Column("revenue_date", sa.Date(), nullable=False),
        sa.Column("category", sa.String(length=80), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column("amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("client", sa.String(length=255), nullable=True),
        sa.Column("reference_no", sa.String(length=80), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *_audit_columns(),
    )
    op.create_index(
        "ix_project_revenues_project_id",
        "project_revenues",
        ["project_id"],
    )
    op.create_index(
        "ix_project_revenues_revenue_date",
        "project_revenues",
        ["revenue_date"],
    )
    op.create_index(
        "ix_project_revenues_project_id_revenue_date",
        "project_revenues",
        ["project_id", "revenue_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_project_revenues_project_id_revenue_date",
        table_name="project_revenues",
    )
    op.drop_index(
        "ix_project_revenues_revenue_date",
        table_name="project_revenues",
    )
    op.drop_index(
        "ix_project_revenues_project_id",
        table_name="project_revenues",
    )
    op.drop_table("project_revenues")

    op.drop_index(
        "ix_project_direct_expenses_project_id_expense_date",
        table_name="project_direct_expenses",
    )
    op.drop_index(
        "ix_project_direct_expenses_expense_date",
        table_name="project_direct_expenses",
    )
    op.drop_index(
        "ix_project_direct_expenses_project_id",
        table_name="project_direct_expenses",
    )
    op.drop_table("project_direct_expenses")

    op.drop_index(
        "ix_attendance_entries_employee_id_work_date",
        table_name="attendance_entries",
    )
    op.drop_index(
        "ix_attendance_entries_project_id_work_date",
        table_name="attendance_entries",
    )
    op.drop_table("attendance_entries")
