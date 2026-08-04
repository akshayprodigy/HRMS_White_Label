"""salary component + template master (F3)

Structured salary components + reusable templates. Seeds the four
canonical earning heads (basic / conveyance 30% / hra 50% / other 20% of
basic) so an equivalent template reproduces the historical flat-column
payroll output. Adds Employee.salary_template_id (nullable, opt-in) — NULL
for every existing employee, so payroll is unchanged until a template is
assigned.

Revision ID: p4q5r6s7t8u9
Revises: o3p4q5r6s7t8
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa

revision = "p4q5r6s7t8u9"
down_revision = "o3p4q5r6s7t8"
branch_labels = None
depends_on = None

# code, name, slot, default_calc_method, default_percent, display_order
COMPONENT_SEED = [
    ("basic", "Basic", "basic", "flat", None, 10),
    ("conveyance", "Conveyance Allowance", "conveyance", "percent_of_basic", 30.0, 20),
    ("hra", "House Rent Allowance", "hra", "percent_of_basic", 50.0, 30),
    ("other", "Other Allowance", "other", "percent_of_basic", 20.0, 40),
]


def upgrade():
    op.create_table(
        "salary_component",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("component_type", sa.String(20), nullable=False, server_default="earning"),
        sa.Column("slot", sa.String(20), nullable=True),
        sa.Column("default_calc_method", sa.String(20), nullable=False, server_default="flat"),
        sa.Column("default_percent", sa.Float(), nullable=True),
        sa.Column("is_taxable", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_salary_component_code"),
    )
    op.create_index("ix_salary_component_code", "salary_component", ["code"], unique=False)
    op.create_index("ix_salary_component_is_active", "salary_component", ["is_active"], unique=False)

    op.create_table(
        "salary_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("code", sa.String(30), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now()),
        sa.UniqueConstraint("code", name="uq_salary_template_code"),
    )
    op.create_index("ix_salary_template_code", "salary_template", ["code"], unique=False)
    op.create_index("ix_salary_template_is_active", "salary_template", ["is_active"], unique=False)

    op.create_table(
        "salary_template_component",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("template_id", sa.Integer(), nullable=False),
        sa.Column("component_id", sa.Integer(), nullable=False),
        sa.Column("calc_method", sa.String(20), nullable=False, server_default="flat"),
        sa.Column("value", sa.Float(), nullable=True),
        sa.Column("percent", sa.Float(), nullable=True),
        sa.Column("display_order", sa.Integer(), nullable=False, server_default="0"),
        sa.ForeignKeyConstraint(["template_id"], ["salary_template.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["component_id"], ["salary_component.id"], ondelete="CASCADE"),
        sa.UniqueConstraint("template_id", "component_id", name="uq_template_component"),
    )
    op.create_index("ix_salary_template_component_template_id", "salary_template_component", ["template_id"], unique=False)
    op.create_index("ix_salary_template_component_component_id", "salary_template_component", ["component_id"], unique=False)

    # Opt-in FK on employee. Nullable — every existing row stays NULL.
    op.add_column(
        "employee",
        sa.Column("salary_template_id", sa.Integer(), nullable=True),
    )
    op.create_index("ix_employee_salary_template_id", "employee", ["salary_template_id"], unique=False)
    op.create_foreign_key(
        "fk_employee_salary_template_id", "employee", "salary_template",
        ["salary_template_id"], ["id"], ondelete="SET NULL",
    )

    # Seed the four canonical earning heads.
    t = sa.table(
        "salary_component",
        sa.column("code", sa.String), sa.column("name", sa.String),
        sa.column("slot", sa.String), sa.column("default_calc_method", sa.String),
        sa.column("default_percent", sa.Float), sa.column("display_order", sa.Integer),
    )
    op.bulk_insert(t, [
        {"code": c, "name": n, "slot": s, "default_calc_method": m,
         "default_percent": p, "display_order": o}
        for (c, n, s, m, p, o) in COMPONENT_SEED
    ])


def downgrade():
    op.drop_constraint("fk_employee_salary_template_id", "employee", type_="foreignkey")
    op.drop_index("ix_employee_salary_template_id", table_name="employee")
    op.drop_column("employee", "salary_template_id")

    op.drop_index("ix_salary_template_component_component_id", table_name="salary_template_component")
    op.drop_index("ix_salary_template_component_template_id", table_name="salary_template_component")
    op.drop_table("salary_template_component")

    op.drop_index("ix_salary_template_is_active", table_name="salary_template")
    op.drop_index("ix_salary_template_code", table_name="salary_template")
    op.drop_table("salary_template")

    op.drop_index("ix_salary_component_is_active", table_name="salary_component")
    op.drop_index("ix_salary_component_code", table_name="salary_component")
    op.drop_table("salary_component")
