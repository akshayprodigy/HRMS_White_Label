"""add statutory filing tables (PF / ESIC / PT)

Pure additive — no existing column touched, no existing row mutated.
Generators READ finalized payroll lines; this migration only stands
up the masters + filing-record tables.

Revision ID: c0x1y2z3a4b5
Revises: b9w0x1y2z3a4
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "c0x1y2z3a4b5"
down_revision = "b9w0x1y2z3a4"
branch_labels = None
depends_on = None


def upgrade():
    # ----- employer_identifier ----------------------------------------
    op.create_table(
        "employer_identifier",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("pf_establishment_code", sa.String(40), nullable=True),
        sa.Column("pf_extension", sa.String(20), nullable=True),
        sa.Column("esic_employer_code", sa.String(40), nullable=True),
        sa.Column("tan", sa.String(20), nullable=True),
        sa.Column("pan", sa.String(20), nullable=True),
        sa.Column("lin", sa.String(20), nullable=True),
        sa.Column("default_pt_state", sa.String(40), nullable=True),
        sa.Column("address_line", sa.String(255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_employer_identifier_name"),
    )

    # ----- statutory_config ------------------------------------------
    op.create_table(
        "statutory_config",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),

        sa.Column("pf_employee_rate", sa.Float(), nullable=False,
                  server_default=sa.text("12.0")),
        sa.Column("pf_employer_rate", sa.Float(), nullable=False,
                  server_default=sa.text("12.0")),
        sa.Column("eps_rate", sa.Float(), nullable=False,
                  server_default=sa.text("8.33")),
        sa.Column("pf_wage_ceiling", sa.Float(), nullable=False,
                  server_default=sa.text("15000.0")),
        sa.Column("eps_wage_ceiling", sa.Float(), nullable=False,
                  server_default=sa.text("15000.0")),
        sa.Column("edli_rate", sa.Float(), nullable=False,
                  server_default=sa.text("0.5")),
        sa.Column("edli_wage_ceiling", sa.Float(), nullable=False,
                  server_default=sa.text("15000.0")),
        sa.Column("epf_admin_rate", sa.Float(), nullable=False,
                  server_default=sa.text("0.5")),

        sa.Column("esic_employee_rate", sa.Float(), nullable=False,
                  server_default=sa.text("0.75")),
        sa.Column("esic_employer_rate", sa.Float(), nullable=False,
                  server_default=sa.text("3.25")),
        sa.Column("esic_wage_ceiling", sa.Float(), nullable=False,
                  server_default=sa.text("21000.0")),

        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_statutory_config_name"),
    )
    op.create_index(
        "ix_statutory_config_effective_from",
        "statutory_config", ["effective_from"],
    )

    # ----- pt_state_slab ---------------------------------------------
    op.create_table(
        "pt_state_slab",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("state", sa.String(40), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("slab_min", sa.Float(), nullable=False),
        sa.Column("slab_max", sa.Float(), nullable=True),
        sa.Column("monthly_amount", sa.Float(), nullable=False),
        sa.Column("gender", sa.String(8), nullable=False,
                  server_default="ALL"),
        sa.Column("month_index", sa.Integer(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False,
                  server_default=sa.true()),
        sa.Column("notes", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "state", "effective_from", "slab_min", "gender", "month_index",
            name="uq_pt_slab",
        ),
    )
    op.create_index("ix_pt_state_slab_state", "pt_state_slab", ["state"])
    op.create_index(
        "ix_pt_state_slab_effective_from",
        "pt_state_slab", ["effective_from"],
    )

    # ----- employee_statutory_detail ---------------------------------
    op.create_table(
        "employee_statutory_detail",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("uan", sa.String(20), nullable=True),
        sa.Column("pf_member_id", sa.String(40), nullable=True),
        sa.Column("esic_ip_number", sa.String(20), nullable=True),
        sa.Column("pt_state", sa.String(40), nullable=True),
        sa.Column("gender", sa.String(8), nullable=False,
                  server_default="ALL"),
        sa.Column("esic_continuation_until", sa.Date(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("employee_id", name="uq_emp_statutory_detail"),
    )

    # ----- statutory_filing ------------------------------------------
    op.create_table(
        "statutory_filing",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "payroll_run_id", sa.Integer(),
            sa.ForeignKey("payrollrun.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("stream", sa.String(10), nullable=False),
        sa.Column("state", sa.String(40), nullable=True),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="generated"),

        sa.Column("file_url", sa.String(512), nullable=True),
        sa.Column("file_name", sa.String(255), nullable=True),
        sa.Column(
            "employer_identifier_id", sa.Integer(),
            sa.ForeignKey("employer_identifier.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "config_id", sa.Integer(),
            sa.ForeignKey("statutory_config.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("summary", sa.JSON(), nullable=True),

        sa.Column("challan_number", sa.String(100), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("paid_amount", sa.Float(), nullable=True),

        sa.Column("generated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column(
            "generated_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint(
            "payroll_run_id", "stream", "state",
            name="uq_statutory_filing_run_stream_state",
        ),
    )
    op.create_index("ix_filing_run", "statutory_filing", ["payroll_run_id"])
    op.create_index("ix_filing_stream", "statutory_filing", ["stream"])
    op.create_index("ix_filing_status", "statutory_filing", ["status"])


def downgrade():
    op.drop_index("ix_filing_status", table_name="statutory_filing")
    op.drop_index("ix_filing_stream", table_name="statutory_filing")
    op.drop_index("ix_filing_run", table_name="statutory_filing")
    op.drop_table("statutory_filing")
    op.drop_table("employee_statutory_detail")
    op.drop_index("ix_pt_state_slab_effective_from", table_name="pt_state_slab")
    op.drop_index("ix_pt_state_slab_state", table_name="pt_state_slab")
    op.drop_table("pt_state_slab")
    op.drop_index(
        "ix_statutory_config_effective_from", table_name="statutory_config"
    )
    op.drop_table("statutory_config")
    op.drop_table("employer_identifier")
