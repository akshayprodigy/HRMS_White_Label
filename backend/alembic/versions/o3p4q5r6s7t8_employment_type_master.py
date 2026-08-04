"""employment type master (F2)

Configurable employment-type master keyed by `code` (matches the existing
Employee.employment_type string). Seeds the 3 existing codes so current
employees resolve unchanged.

Revision ID: o3p4q5r6s7t8
Revises: n2o3p4q5r6s7
Create Date: 2026-08-03
"""
from alembic import op
import sqlalchemy as sa

revision = "o3p4q5r6s7t8"
down_revision = "n2o3p4q5r6s7"
branch_labels = None
depends_on = None

SEED = [
    # code, name, is_on_payroll, statutory_enabled, flat_tds_rate
    ("permanent", "Permanent (Full-time)", True, True, None),
    ("contractual", "Contractual", True, False, 0.10),
    ("advisor", "Advisor / Consultant", False, False, 0.10),
]


def upgrade():
    op.create_table(
        "employment_type",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(20), nullable=False),
        sa.Column("name", sa.String(60), nullable=False),
        sa.Column("is_on_payroll", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("statutory_enabled", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("flat_tds_rate", sa.Float(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_employment_type_code"),
    )
    op.create_index("ix_employment_type_code", "employment_type", ["code"], unique=False)

    t = sa.table(
        "employment_type",
        sa.column("code", sa.String), sa.column("name", sa.String),
        sa.column("is_on_payroll", sa.Boolean), sa.column("statutory_enabled", sa.Boolean),
        sa.column("flat_tds_rate", sa.Float),
    )
    op.bulk_insert(t, [
        {"code": c, "name": n, "is_on_payroll": p, "statutory_enabled": s, "flat_tds_rate": r}
        for (c, n, p, s, r) in SEED
    ])


def downgrade():
    op.drop_index("ix_employment_type_code", table_name="employment_type")
    op.drop_table("employment_type")
