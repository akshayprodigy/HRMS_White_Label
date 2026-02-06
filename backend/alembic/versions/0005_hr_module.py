"""hr module

Revision ID: 0005_hr_module
Revises: 0004_audit_logs
Create Date: 2026-02-05

"""

from __future__ import annotations

import sqlalchemy as sa

from alembic import op

revision = "0005_hr_module"
down_revision = "0004_audit_logs"
branch_labels = None
depends_on = None


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
        "employees",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employee_code", sa.String(length=50), nullable=True),
        sa.Column("first_name", sa.String(length=100), nullable=False),
        sa.Column("last_name", sa.String(length=100), nullable=True),
        sa.Column("email", sa.String(length=255), nullable=True),
        sa.Column("phone", sa.String(length=30), nullable=True),
        sa.Column("date_of_birth", sa.Date(), nullable=True),
        sa.Column("gender", sa.String(length=20), nullable=True),
        sa.Column("address_line1", sa.String(length=255), nullable=True),
        sa.Column("address_line2", sa.String(length=255), nullable=True),
        sa.Column("city", sa.String(length=100), nullable=True),
        sa.Column("state", sa.String(length=100), nullable=True),
        sa.Column("postal_code", sa.String(length=20), nullable=True),
        sa.Column("country", sa.String(length=100), nullable=True),
        sa.Column("bank_name", sa.String(length=150), nullable=True),
        sa.Column("bank_account_number", sa.String(length=64), nullable=True),
        sa.Column("bank_ifsc", sa.String(length=32), nullable=True),
        sa.Column("bank_branch", sa.String(length=150), nullable=True),
        sa.Column(
            "emergency_contact_name",
            sa.String(length=150),
            nullable=True,
        ),
        sa.Column(
            "emergency_contact_relation",
            sa.String(length=80),
            nullable=True,
        ),
        sa.Column(
            "emergency_contact_phone",
            sa.String(length=30),
            nullable=True,
        ),
        sa.Column("employment_type", sa.String(length=30), nullable=False),
        sa.Column("employment_status", sa.String(length=30), nullable=False),
        sa.Column("joining_date", sa.Date(), nullable=False),
        sa.Column("exit_date", sa.Date(), nullable=True),
        *_audit_columns(),
        sa.UniqueConstraint(
            "employee_code",
            name="uq_employees_employee_code",
        ),
    )
    op.create_index("ix_employees_email", "employees", ["email"])
    op.create_index("ix_employees_phone", "employees", ["phone"])
    op.create_index(
        "ix_employees_employment_status",
        "employees",
        ["employment_status"],
    )

    op.create_table(
        "employee_documents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("document_type", sa.String(length=80), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=True),
        sa.Column("file_ref", sa.String(length=500), nullable=False),
        sa.Column("mime_type", sa.String(length=100), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=True),
        sa.Column("expires_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_employee_documents_employee",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_employee_documents_employee_id",
        "employee_documents",
        ["employee_id"],
    )
    op.create_index(
        "ix_employee_documents_document_type",
        "employee_documents",
        ["document_type"],
    )

    op.create_table(
        "employee_assets",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("employee_id", sa.BigInteger(), nullable=False),
        sa.Column("asset_category", sa.String(length=30), nullable=False),
        sa.Column("asset_name", sa.String(length=255), nullable=False),
        sa.Column("asset_tag", sa.String(length=80), nullable=True),
        sa.Column("issued_on", sa.Date(), nullable=False),
        sa.Column("returned_on", sa.Date(), nullable=True),
        sa.Column("notes", sa.String(length=500), nullable=True),
        *_audit_columns(),
        sa.ForeignKeyConstraint(
            ["employee_id"],
            ["employees.id"],
            name="fk_employee_assets_employee",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_employee_assets_employee_id",
        "employee_assets",
        ["employee_id"],
    )
    op.create_index(
        "ix_employee_assets_asset_category",
        "employee_assets",
        ["asset_category"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_employee_assets_asset_category",
        table_name="employee_assets",
    )
    op.drop_index(
        "ix_employee_assets_employee_id",
        table_name="employee_assets",
    )
    op.drop_table("employee_assets")

    op.drop_index(
        "ix_employee_documents_document_type",
        table_name="employee_documents",
    )
    op.drop_index(
        "ix_employee_documents_employee_id",
        table_name="employee_documents",
    )
    op.drop_table("employee_documents")

    op.drop_index("ix_employees_employment_status", table_name="employees")
    op.drop_index("ix_employees_phone", table_name="employees")
    op.drop_index("ix_employees_email", table_name="employees")
    op.drop_table("employees")
