"""add shift_template and employee_shift_assignment tables

Foundation for the 24x7 shift engine. This migration ONLY creates the
two tables (templates + per-employee assignments). Attendance computation
and cross-midnight handling are deliberately not touched here.

Revision ID: x5s6t7u8v9w0
Revises: w4r5s6t7u8v9
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "x5s6t7u8v9w0"
down_revision = "w4r5s6t7u8v9"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "shift_template",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column(
            "is_overnight",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
        sa.Column(
            "break_minutes",
            sa.Integer(),
            nullable=False,
            server_default="60",
        ),
        sa.Column(
            "grace_in_minutes",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
        sa.Column(
            "grace_out_minutes",
            sa.Integer(),
            nullable=False,
            server_default="10",
        ),
        sa.Column(
            "full_day_hours",
            sa.Float(),
            nullable=False,
            server_default="9.0",
        ),
        sa.Column(
            "half_day_hours",
            sa.Float(),
            nullable=False,
            server_default="4.5",
        ),
        sa.Column("weekly_offs", sa.JSON(), nullable=False),
        sa.Column(
            "is_active",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("created_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["created_by_id"], ["user.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("name", name="uq_shift_template_name"),
    )
    op.create_index(
        "ix_shift_template_name", "shift_template", ["name"], unique=False
    )
    op.create_index(
        "ix_shift_template_is_overnight",
        "shift_template",
        ["is_overnight"],
        unique=False,
    )

    op.create_table(
        "employee_shift_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), nullable=False),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("assigned_by_id", sa.Integer(), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["employee_id"], ["user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["shift_template_id"],
            ["shift_template.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["assigned_by_id"], ["user.id"], ondelete="SET NULL"
        ),
    )
    op.create_index(
        "ix_esa_employee_id",
        "employee_shift_assignment",
        ["employee_id"],
        unique=False,
    )
    op.create_index(
        "ix_esa_shift_template_id",
        "employee_shift_assignment",
        ["shift_template_id"],
        unique=False,
    )
    op.create_index(
        "ix_esa_effective_from",
        "employee_shift_assignment",
        ["effective_from"],
        unique=False,
    )
    op.create_index(
        "ix_esa_effective_to",
        "employee_shift_assignment",
        ["effective_to"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_esa_effective_to", table_name="employee_shift_assignment")
    op.drop_index(
        "ix_esa_effective_from", table_name="employee_shift_assignment"
    )
    op.drop_index(
        "ix_esa_shift_template_id", table_name="employee_shift_assignment"
    )
    op.drop_index("ix_esa_employee_id", table_name="employee_shift_assignment")
    op.drop_table("employee_shift_assignment")
    op.drop_index("ix_shift_template_is_overnight", table_name="shift_template")
    op.drop_index("ix_shift_template_name", table_name="shift_template")
    op.drop_table("shift_template")
