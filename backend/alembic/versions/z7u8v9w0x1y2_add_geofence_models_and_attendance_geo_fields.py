"""add geofence models + attendance geo fields

Step 3 of the 24x7 shift engine: geo-fencing.

Adds:
- geofence_location           : master list of allowed sites
- employee_geo_config         : per-employee enforcement mode + toggle
- employee_geo_fence_link     : allowlist (employee -> [fence,...])
- attendance.is_mock_location, matched_fence_id, distance_to_fence_meters,
                  geo_flag (punch-in)
- attendance.punch_out_latitude, longitude, accuracy, is_mock,
                  matched_fence_id, distance_to_fence_meters, geo_flag

Backward compatibility
----------------------
All new attendance columns are NULL / FALSE for existing rows. Employees
without an employee_geo_config row are treated as "no geo configured" —
the punch flow behaves exactly as today.

Revision ID: z7u8v9w0x1y2
Revises: y6t7u8v9w0x1
Create Date: 2026-06-30
"""
from alembic import op
import sqlalchemy as sa


revision = "z7u8v9w0x1y2"
down_revision = "y6t7u8v9w0x1"
branch_labels = None
depends_on = None


def upgrade():
    # ----- geofence_location ------------------------------------------
    op.create_table(
        "geofence_location",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("latitude", sa.Float(), nullable=False),
        sa.Column("longitude", sa.Float(), nullable=False),
        sa.Column("radius_meters", sa.Integer(), nullable=False),
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
        sa.UniqueConstraint("name", name="uq_geofence_location_name"),
    )
    op.create_index(
        "ix_geofence_location_name",
        "geofence_location",
        ["name"],
        unique=False,
    )

    # ----- employee_geo_config ----------------------------------------
    op.create_table(
        "employee_geo_config",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column(
            "enforcement_mode",
            sa.String(32),
            nullable=False,
            server_default="strict",
        ),
        sa.Column(
            "geo_enabled",
            sa.Boolean(),
            nullable=False,
            server_default=sa.true(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.Column("updated_by_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(
            ["user_id"], ["user.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["updated_by_id"], ["user.id"], ondelete="SET NULL"
        ),
    )

    # ----- employee_geo_fence_link ------------------------------------
    op.create_table(
        "employee_geo_fence_link",
        sa.Column("user_id", sa.Integer(), primary_key=True),
        sa.Column("geofence_location_id", sa.Integer(), primary_key=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.current_timestamp(),
        ),
        sa.ForeignKeyConstraint(
            ["user_id"], ["employee_geo_config.user_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["geofence_location_id"],
            ["geofence_location.id"],
            ondelete="CASCADE",
        ),
    )

    # ----- attendance.* new geo columns -------------------------------
    op.add_column(
        "attendance",
        sa.Column(
            "is_mock_location",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "attendance",
        sa.Column("matched_fence_id", sa.Integer(), nullable=True),
    )
    op.add_column(
        "attendance",
        sa.Column(
            "distance_to_fence_meters", sa.Float(), nullable=True
        ),
    )
    op.add_column(
        "attendance",
        sa.Column("geo_flag", sa.String(32), nullable=True),
    )
    op.add_column(
        "attendance",
        sa.Column("punch_out_latitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "attendance",
        sa.Column("punch_out_longitude", sa.Float(), nullable=True),
    )
    op.add_column(
        "attendance",
        sa.Column("punch_out_accuracy", sa.Float(), nullable=True),
    )
    op.add_column(
        "attendance",
        sa.Column(
            "punch_out_is_mock",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "attendance",
        sa.Column(
            "punch_out_matched_fence_id", sa.Integer(), nullable=True
        ),
    )
    op.add_column(
        "attendance",
        sa.Column(
            "punch_out_distance_to_fence_meters",
            sa.Float(),
            nullable=True,
        ),
    )
    op.add_column(
        "attendance",
        sa.Column("punch_out_geo_flag", sa.String(32), nullable=True),
    )

    op.create_foreign_key(
        "fk_attendance_matched_fence",
        source_table="attendance",
        referent_table="geofence_location",
        local_cols=["matched_fence_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_attendance_punch_out_matched_fence",
        source_table="attendance",
        referent_table="geofence_location",
        local_cols=["punch_out_matched_fence_id"],
        remote_cols=["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_attendance_matched_fence_id",
        "attendance",
        ["matched_fence_id"],
        unique=False,
    )
    op.create_index(
        "ix_attendance_geo_flag",
        "attendance",
        ["geo_flag"],
        unique=False,
    )


def downgrade():
    op.drop_index("ix_attendance_geo_flag", table_name="attendance")
    op.drop_index(
        "ix_attendance_matched_fence_id", table_name="attendance"
    )
    op.drop_constraint(
        "fk_attendance_punch_out_matched_fence",
        "attendance",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_attendance_matched_fence",
        "attendance",
        type_="foreignkey",
    )
    for col in [
        "punch_out_geo_flag",
        "punch_out_distance_to_fence_meters",
        "punch_out_matched_fence_id",
        "punch_out_is_mock",
        "punch_out_accuracy",
        "punch_out_longitude",
        "punch_out_latitude",
        "geo_flag",
        "distance_to_fence_meters",
        "matched_fence_id",
        "is_mock_location",
    ]:
        op.drop_column("attendance", col)

    op.drop_table("employee_geo_fence_link")
    op.drop_table("employee_geo_config")
    op.drop_index(
        "ix_geofence_location_name", table_name="geofence_location"
    )
    op.drop_table("geofence_location")
