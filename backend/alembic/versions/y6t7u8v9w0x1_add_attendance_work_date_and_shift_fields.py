"""add work_date + shift attribution columns to attendance

Part of the 24x7 shift engine. Existing day-shift attendance records
are backfilled with work_date = DATE(captured_at) so legacy queries
keep working. New columns:

- work_date            : logical date (primary for queries/payroll)
- shift_template_id    : snapshot of the shift the resolver used (nullable)
- is_cross_midnight    : true when the punch attribution crossed midnight
- attribution_flag     : NULL when confident; otherwise 'no_shift',
                         'outside_window', or 'ambiguous'

Backfill rule
-------------
For every existing row we set:
    work_date         = DATE(captured_at)   (calendar date)
    shift_template_id = NULL                (legacy: no shift was assigned)
    is_cross_midnight = FALSE
    attribution_flag  = 'no_shift'

This keeps every legacy record behaviourally identical to the
pre-shift world: HR can review them via the flagged queue if they
want to backfill shift assignments retroactively.

Revision ID: y6t7u8v9w0x1
Revises: x5s6t7u8v9w0
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "y6t7u8v9w0x1"
down_revision = "x5s6t7u8v9w0"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Add columns nullable so the backfill below has room to run.
    op.add_column(
        "attendance",
        sa.Column("work_date", sa.Date(), nullable=True),
    )
    op.add_column(
        "attendance",
        sa.Column(
            "shift_template_id", sa.Integer(), nullable=True
        ),
    )
    op.add_column(
        "attendance",
        sa.Column(
            "is_cross_midnight",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "attendance",
        sa.Column("attribution_flag", sa.String(32), nullable=True),
    )

    # 2. Backfill historical rows. Treat them as legacy day-shift records:
    #    work_date = calendar date of captured_at, no shift, NO_SHIFT flag
    #    so HR can spot them in the review queue.
    op.execute(
        "UPDATE attendance "
        "SET work_date = DATE(captured_at), "
        "    attribution_flag = 'no_shift' "
        "WHERE work_date IS NULL"
    )

    # 3. Lock work_date NOT NULL now that every row has a value.
    op.alter_column(
        "attendance",
        "work_date",
        existing_type=sa.Date(),
        nullable=False,
    )

    # 4. FK to shift_template (added in revision x5s6t7u8v9w0).
    op.create_foreign_key(
        "fk_attendance_shift_template",
        source_table="attendance",
        referent_table="shift_template",
        local_cols=["shift_template_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )

    # 5. Indexes for the query patterns we'll add (payroll month range,
    #    flagged-queue filter).
    op.create_index(
        "ix_attendance_work_date", "attendance", ["work_date"], unique=False
    )
    op.create_index(
        "ix_attendance_shift_template_id",
        "attendance",
        ["shift_template_id"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_attribution_flag",
        "attendance",
        ["attribution_flag"],
        unique=False,
    )

    # AttendanceCorrectionRequest already has a `date` column. Add an
    # optional `requested_work_date` so corrections can change the
    # attribution date itself (not just the time). Nullable for back-compat.
    op.add_column(
        "attendancecorrectionrequest",
        sa.Column("requested_work_date", sa.Date(), nullable=True),
    )


def downgrade():
    op.drop_column("attendancecorrectionrequest", "requested_work_date")

    op.drop_index(
        "ix_attendance_attribution_flag", table_name="attendance"
    )
    op.drop_index(
        "ix_attendance_shift_template_id", table_name="attendance"
    )
    op.drop_index("ix_attendance_work_date", table_name="attendance")
    op.drop_constraint(
        "fk_attendance_shift_template",
        "attendance",
        type_="foreignkey",
    )
    op.drop_column("attendance", "attribution_flag")
    op.drop_column("attendance", "is_cross_midnight")
    op.drop_column("attendance", "shift_template_id")
    op.drop_column("attendance", "work_date")
