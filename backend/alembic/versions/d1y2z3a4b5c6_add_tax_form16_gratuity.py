"""add tax/Form 16/Form 24Q/gratuity tables (additive)

Pure additive. Touches no existing column, no existing row. Reads
finalized payroll at runtime.

Revision ID: d1y2z3a4b5c6
Revises: c0x1y2z3a4b5
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "d1y2z3a4b5c6"
down_revision = "c0x1y2z3a4b5"
branch_labels = None
depends_on = None


def upgrade():
    # ----- tax_slab_config -------------------------------------------
    op.create_table(
        "tax_slab_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fy", sa.String(8), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slabs_json", sa.JSON(), nullable=False),
        sa.Column(
            "standard_deduction_old", sa.Float(),
            nullable=False, server_default=sa.text("50000.0"),
        ),
        sa.Column(
            "standard_deduction_new", sa.Float(),
            nullable=False, server_default=sa.text("75000.0"),
        ),
        sa.Column(
            "rebate_87a_old_threshold", sa.Float(),
            nullable=False, server_default=sa.text("500000.0"),
        ),
        sa.Column(
            "rebate_87a_old_max", sa.Float(),
            nullable=False, server_default=sa.text("12500.0"),
        ),
        sa.Column(
            "rebate_87a_new_threshold", sa.Float(),
            nullable=False, server_default=sa.text("700000.0"),
        ),
        sa.Column(
            "rebate_87a_new_max", sa.Float(),
            nullable=False, server_default=sa.text("25000.0"),
        ),
        sa.Column(
            "cess_rate", sa.Float(),
            nullable=False, server_default=sa.text("4.0"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("fy", name="uq_tax_slab_fy"),
    )
    op.create_index("ix_tax_slab_fy", "tax_slab_config", ["fy"])

    # ----- section_limit_config --------------------------------------
    op.create_table(
        "section_limit_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fy", sa.String(8), nullable=False),
        sa.Column("section_code", sa.String(40), nullable=False),
        sa.Column("limit_amount", sa.Float(), nullable=False),
        sa.Column(
            "is_percentage", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        sa.Column(
            "applies_to", sa.String(8),
            nullable=False, server_default="BOTH",
        ),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint(
            "fy", "section_code", name="uq_section_limit_fy_code",
        ),
    )
    op.create_index("ix_section_limit_fy", "section_limit_config", ["fy"])

    # ----- gratuity_config -------------------------------------------
    op.create_table(
        "gratuity_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column(
            "statutory_cap", sa.Float(),
            nullable=False, server_default=sa.text("2000000.0"),
        ),
        sa.Column(
            "eligibility_years", sa.Integer(),
            nullable=False, server_default=sa.text("5"),
        ),
        sa.Column(
            "days_basis", sa.Integer(),
            nullable=False, server_default=sa.text("26"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("effective_from", name="uq_gratuity_effective"),
    )

    # ----- employee_tax_declaration ----------------------------------
    op.create_table(
        "employee_tax_declaration",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fy", sa.String(8), nullable=False),
        sa.Column(
            "regime", sa.String(8), nullable=False, server_default="new",
        ),
        sa.Column(
            "declarations_json", sa.JSON(), nullable=False,
            server_default=sa.text("'{}'::json"),
        ),
        sa.Column(
            "monthly_rent_paid", sa.Float(),
            nullable=False, server_default=sa.text("0.0"),
        ),
        sa.Column(
            "rented_in_metro", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        sa.Column("landlord_pan", sa.String(20), nullable=True),
        sa.Column(
            "other_income_annual", sa.Float(),
            nullable=False, server_default=sa.text("0.0"),
        ),
        sa.Column(
            "previous_employer_income", sa.Float(),
            nullable=False, server_default=sa.text("0.0"),
        ),
        sa.Column(
            "previous_employer_tds", sa.Float(),
            nullable=False, server_default=sa.text("0.0"),
        ),
        sa.Column(
            "status", sa.String(20),
            nullable=False, server_default="draft",
        ),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "verified_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("rejection_reason", sa.String(500), nullable=True),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("employee_id", "fy", name="uq_emp_tax_decl_fy"),
    )
    op.create_index("ix_emp_tax_decl_emp", "employee_tax_declaration", ["employee_id"])
    op.create_index("ix_emp_tax_decl_fy", "employee_tax_declaration", ["fy"])
    op.create_index("ix_emp_tax_decl_status", "employee_tax_declaration", ["status"])

    # ----- form16_record ---------------------------------------------
    op.create_table(
        "form16_record",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("fy", sa.String(8), nullable=False),
        sa.Column("reference_number", sa.String(80), nullable=True),
        sa.Column("part_b_url", sa.String(512), nullable=True),
        sa.Column("part_b_data", sa.JSON(), nullable=True),
        sa.Column("part_b_generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("part_a_url", sa.String(512), nullable=True),
        sa.Column("part_a_uploaded_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("traces_certificate_number", sa.String(60), nullable=True),
        sa.Column(
            "status", sa.String(30),
            nullable=False, server_default="pending_part_a",
        ),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "missing_pan_flag", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        sa.Column(
            "generated_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("employee_id", "fy", name="uq_form16_emp_fy"),
        sa.UniqueConstraint("reference_number", name="uq_form16_ref"),
    )
    op.create_index("ix_form16_emp", "form16_record", ["employee_id"])
    op.create_index("ix_form16_fy", "form16_record", ["fy"])
    op.create_index("ix_form16_status", "form16_record", ["status"])

    # ----- form_24q_export -------------------------------------------
    op.create_table(
        "form_24q_export",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("fy", sa.String(8), nullable=False),
        sa.Column("quarter", sa.Integer(), nullable=False),
        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column("summary", sa.JSON(), nullable=True),
        sa.Column(
            "status", sa.String(20),
            nullable=False, server_default="draft",
        ),
        sa.Column("challan_number", sa.String(100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "generated_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.UniqueConstraint("fy", "quarter", name="uq_24q_fy_quarter"),
    )
    op.create_index("ix_24q_fy", "form_24q_export", ["fy"])
    op.create_index("ix_24q_status", "form_24q_export", ["status"])

    # ----- gratuity_computation --------------------------------------
    op.create_table(
        "gratuity_computation",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "config_id", sa.Integer(),
            sa.ForeignKey("gratuity_config.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "resignation_id", sa.Integer(),
            sa.ForeignKey("resignation.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("last_drawn_basic_da", sa.Float(), nullable=False),
        sa.Column("raw_years", sa.Float(), nullable=False),
        sa.Column("rounded_years", sa.Integer(), nullable=False),
        sa.Column("is_eligible", sa.Boolean(), nullable=False),
        sa.Column("computed_amount", sa.Float(), nullable=False),
        sa.Column("capped_amount", sa.Float(), nullable=False),
        sa.Column(
            "cap_applied", sa.Boolean(),
            nullable=False, server_default=sa.false(),
        ),
        sa.Column(
            "status", sa.String(20),
            nullable=False, server_default="accrued",
        ),
        sa.Column("notes", sa.String(500), nullable=True),
        sa.Column(
            "computed_at", sa.DateTime(timezone=True),
            nullable=False, server_default=sa.func.now(),
        ),
        sa.Column(
            "computed_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_gratuity_comp_emp", "gratuity_computation", ["employee_id"])
    op.create_index("ix_gratuity_comp_as_of", "gratuity_computation", ["as_of"])
    op.create_index("ix_gratuity_comp_resignation", "gratuity_computation", ["resignation_id"])
    op.create_index("ix_gratuity_comp_status", "gratuity_computation", ["status"])


def downgrade():
    op.drop_index("ix_gratuity_comp_status", table_name="gratuity_computation")
    op.drop_index("ix_gratuity_comp_resignation", table_name="gratuity_computation")
    op.drop_index("ix_gratuity_comp_as_of", table_name="gratuity_computation")
    op.drop_index("ix_gratuity_comp_emp", table_name="gratuity_computation")
    op.drop_table("gratuity_computation")
    op.drop_index("ix_24q_status", table_name="form_24q_export")
    op.drop_index("ix_24q_fy", table_name="form_24q_export")
    op.drop_table("form_24q_export")
    op.drop_index("ix_form16_status", table_name="form16_record")
    op.drop_index("ix_form16_fy", table_name="form16_record")
    op.drop_index("ix_form16_emp", table_name="form16_record")
    op.drop_table("form16_record")
    op.drop_index("ix_emp_tax_decl_status", table_name="employee_tax_declaration")
    op.drop_index("ix_emp_tax_decl_fy", table_name="employee_tax_declaration")
    op.drop_index("ix_emp_tax_decl_emp", table_name="employee_tax_declaration")
    op.drop_table("employee_tax_declaration")
    op.drop_table("gratuity_config")
    op.drop_index("ix_section_limit_fy", table_name="section_limit_config")
    op.drop_table("section_limit_config")
    op.drop_index("ix_tax_slab_fy", table_name="tax_slab_config")
    op.drop_table("tax_slab_config")
