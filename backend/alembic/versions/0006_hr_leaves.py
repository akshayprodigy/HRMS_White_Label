"""hr leaves

Revision ID: 0006_hr_leaves
Revises: 0005_hr_module
Create Date: 2026-02-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0006_hr_leaves"
down_revision = "0005_hr_module"
branch_labels = None
depends_on = None

_FK_LEAVE_TYPES_ID = "leave_types.id"


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
        "leave_types",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("code", sa.String(length=30), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("description", sa.String(length=255), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        *_audit_columns(),
        sa.UniqueConstraint("code", name="uq_leave_types_code"),
    )
    op.create_index("ix_leave_types_is_active", "leave_types", ["is_active"])

    op.create_table(
        "leave_policies",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("leave_type_id", sa.BigInteger(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column(
            "monthly_credit_days",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        sa.Column("max_balance_days", sa.Numeric(10, 2), nullable=True),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("1"),
        ),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            [_FK_LEAVE_TYPES_ID],
            name="fk_leave_policies_leave_type",
        ),
    )
    op.create_index(
        "ix_leave_policies_leave_type_id",
        "leave_policies",
        ["leave_type_id"],
    )
    op.create_index(
        "ix_leave_policies_is_active",
        "leave_policies",
        ["is_active"],
    )

    op.create_table(
        "leave_balances",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("leave_type_id", sa.BigInteger(), nullable=False),
        sa.Column(
            "balance_days",
            sa.Numeric(10, 2),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_leave_balances_employee",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            [_FK_LEAVE_TYPES_ID],
            name="fk_leave_balances_leave_type",
        ),
        sa.UniqueConstraint(
            "employee_id",
            "leave_type_id",
            name="uq_leave_balances_employee_leave_type",
        ),
    )
    op.create_index(
        "ix_leave_balances_employee_id",
        "leave_balances",
        ["employee_id"],
    )
    op.create_index(
        "ix_leave_balances_leave_type_id",
        "leave_balances",
        ["leave_type_id"],
    )

    op.create_table(
        "leave_requests",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("leave_type_id", sa.BigInteger(), nullable=False),
        sa.Column("date_from", sa.Date(), nullable=False),
        sa.Column("date_to", sa.Date(), nullable=False),
        sa.Column("days", sa.Numeric(10, 2), nullable=False),
        sa.Column("reason", sa.String(length=500), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column(
            "applied_at",
            sa.DateTime(),
            nullable=False,
            server_default=sa.text("CURRENT_TIMESTAMP"),
        ),
        sa.Column("decided_at", sa.DateTime(), nullable=True),
        sa.Column("decided_by_user_id", sa.BigInteger(), nullable=True),
        sa.Column("decision_comment", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_leave_requests_employee",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["leave_type_id"],
            [_FK_LEAVE_TYPES_ID],
            name="fk_leave_requests_leave_type",
        ),
        sa.ForeignKeyConstraint(
            ["decided_by_user_id"],
            ["users.id"],
            name="fk_leave_requests_decided_by_user",
        ),
    )
    op.create_index(
        "ix_leave_requests_employee_id",
        "leave_requests",
        ["employee_id"],
    )
    op.create_index(
        "ix_leave_requests_leave_type_id",
        "leave_requests",
        ["leave_type_id"],
    )
    op.create_index("ix_leave_requests_status", "leave_requests", ["status"])
    op.create_index(
        "ix_leave_requests_date_from",
        "leave_requests",
        ["date_from"],
    )
    op.create_index(
        "ix_leave_requests_date_to",
        "leave_requests",
        ["date_to"],
    )

    op.create_table(
        "holiday_calendars",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("holiday_date", sa.Date(), nullable=False),
        sa.Column("name", sa.String(length=150), nullable=False),
        sa.Column(
            "is_optional",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("0"),
        ),
        *_audit_columns(),
        sa.UniqueConstraint(
            "holiday_date",
            name="uq_holiday_calendars_holiday_date",
        ),
    )
    op.create_index(
        "ix_holiday_calendars_holiday_date",
        "holiday_calendars",
        ["holiday_date"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_holiday_calendars_holiday_date",
        table_name="holiday_calendars",
    )
    op.drop_table("holiday_calendars")

    op.drop_index("ix_leave_requests_date_to", table_name="leave_requests")
    op.drop_index("ix_leave_requests_date_from", table_name="leave_requests")
    op.drop_index("ix_leave_requests_status", table_name="leave_requests")
    op.drop_index(
        "ix_leave_requests_leave_type_id",
        table_name="leave_requests",
    )
    op.drop_index("ix_leave_requests_employee_id", table_name="leave_requests")
    op.drop_table("leave_requests")

    op.drop_index(
        "ix_leave_balances_leave_type_id",
        table_name="leave_balances",
    )
    op.drop_index("ix_leave_balances_employee_id", table_name="leave_balances")
    op.drop_table("leave_balances")

    op.drop_index("ix_leave_policies_is_active", table_name="leave_policies")
    op.drop_index(
        "ix_leave_policies_leave_type_id",
        table_name="leave_policies",
    )
    op.drop_table("leave_policies")

    op.drop_index("ix_leave_types_is_active", table_name="leave_types")
    op.drop_table("leave_types")
