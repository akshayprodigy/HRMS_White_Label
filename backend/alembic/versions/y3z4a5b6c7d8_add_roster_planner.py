"""roster planner (W7)

Creates roster_entry (per-employee-per-day plan) + roster_change_request
(employee-initiated, head-approved edits), and seeds the 'roster manage'
permission granted to HR / Super Admin / DEPT_HEAD. Functional heads get
access via F1 department-head scoping, not this permission.

Revision ID: y3z4a5b6c7d8
Revises: x2y3z4a5b6c7
Create Date: 2026-08-06
"""
from alembic import op
import sqlalchemy as sa

revision = "y3z4a5b6c7d8"
down_revision = "x2y3z4a5b6c7"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "roster_entry",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("shift_template_id", sa.Integer(), nullable=True),
        sa.Column("is_week_off", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("status", sa.String(16), nullable=False,
                  server_default="published"),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("assigned_by_id", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["shift_template_id"], ["shift_template.id"],
                                ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["assigned_by_id"], ["user.id"],
                                ondelete="SET NULL"),
        sa.UniqueConstraint("employee_id", "work_date",
                            name="uq_roster_entry_emp_date"),
    )
    op.create_index("ix_roster_entry_employee_id", "roster_entry", ["employee_id"])
    op.create_index("ix_roster_entry_work_date", "roster_entry", ["work_date"])
    op.create_index("ix_roster_entry_status", "roster_entry", ["status"])

    op.create_table(
        "roster_change_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employee_id", sa.Integer(), nullable=False),
        sa.Column("roster_entry_id", sa.Integer(), nullable=True),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("current_shift_template_id", sa.Integer(), nullable=True),
        sa.Column("requested_shift_template_id", sa.Integer(), nullable=True),
        sa.Column("requested_week_off", sa.Boolean(), nullable=False,
                  server_default=sa.false()),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column("status", sa.String(20), nullable=False,
                  server_default="pending"),
        sa.Column("decided_by_id", sa.Integer(), nullable=True),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("decision_note", sa.String(500), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["employee_id"], ["user.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["roster_entry_id"], ["roster_entry.id"],
                                ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["current_shift_template_id"],
                                ["shift_template.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["requested_shift_template_id"],
                                ["shift_template.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["decided_by_id"], ["user.id"],
                                ondelete="SET NULL"),
    )
    op.create_index("ix_roster_change_request_status",
                    "roster_change_request", ["status"])
    op.create_index("ix_roster_change_request_employee_id",
                    "roster_change_request", ["employee_id"])

    # Seed 'roster manage' permission + grants (idempotent).
    op.execute(
        "INSERT INTO permission (name, description) "
        "VALUES ('roster manage', 'Plan/publish weekly-monthly rosters for a team') "
        "ON DUPLICATE KEY UPDATE description=VALUES(description)"
    )
    op.execute(
        "INSERT IGNORE INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        "WHERE r.name IN ('HR', 'Super Admin', 'DEPT_HEAD') "
        "AND p.name = 'roster manage'"
    )


def downgrade():
    # Drop the tables directly — their indexes (some of which back the FK
    # columns and so cannot be dropped independently on MariaDB) go with
    # them. roster_change_request first (it FKs roster_entry).
    op.drop_table("roster_change_request")
    op.drop_table("roster_entry")
    op.execute("DELETE FROM permission WHERE name = 'roster manage'")
