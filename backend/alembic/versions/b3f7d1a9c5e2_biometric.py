"""biometric devices, mappings, raw punches + 'biometric manage' permission

Roadmap v2 Phase 4, Task 1.

Revision ID: b3f7d1a9c5e2
Revises: e5b9c3d7a1f4
Create Date: 2026-11-14
"""
from alembic import op
import sqlalchemy as sa

revision = "b3f7d1a9c5e2"
down_revision = "e5b9c3d7a1f4"
branch_labels = None
depends_on = None

_ROLES = "('HR', 'Super Admin')"
_PERM = "biometric manage"


def upgrade():
    op.create_table(
        "biometric_device",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("serial", sa.String(64), nullable=False, unique=True),
        sa.Column("name", sa.String(120)),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("utc_offset_minutes", sa.Integer, nullable=False),
        sa.Column("ip_allowlist", sa.String(500)),
        sa.Column("location_note", sa.String(200)),
        sa.Column("last_seen_at", sa.DateTime(timezone=True)),
        sa.Column("last_ip", sa.String(64)),
        sa.Column("firmware", sa.String(120)),
        sa.Column("attlog_stamp", sa.String(32)),
        sa.Column("operlog_stamp", sa.String(32)),
        sa.Column("offline_alerted_at", sa.DateTime(timezone=True)),
        sa.Column("approved_by_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="SET NULL")),
        sa.Column("approved_at", sa.DateTime(timezone=True)),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  server_default=sa.func.now(), nullable=False),
    )
    op.create_index("ix_biometric_device_status", "biometric_device", ["status"])
    op.create_index("ix_biometric_device_last_seen_at", "biometric_device",
                    ["last_seen_at"])

    op.create_table(
        "biometric_device_user",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("biometric_device.id", ondelete="CASCADE"),
                  nullable=False),
        sa.Column("pin", sa.String(32), nullable=False),
        sa.Column("name", sa.String(120)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("device_id", "pin"),
    )

    op.create_table(
        "biometric_user_map",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("biometric_device.id", ondelete="CASCADE")),
        sa.Column("device_key", sa.Integer,
                  sa.Computed("COALESCE(device_id, 0)", persisted=True)),
        sa.Column("pin", sa.String(32), nullable=False),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_by_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="SET NULL")),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("device_key", "pin"),
    )
    op.create_index("ix_biometric_user_map_user_id", "biometric_user_map",
                    ["user_id"])

    op.create_table(
        "biometric_punch",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("dedupe_key", sa.String(64), nullable=False, unique=True),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column("device_id", sa.Integer,
                  sa.ForeignKey("biometric_device.id", ondelete="SET NULL")),
        sa.Column("import_batch", sa.String(36)),
        sa.Column("pin", sa.String(32), nullable=False),
        sa.Column("punch_time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("device_status", sa.String(8)),
        sa.Column("verify_type", sa.String(8)),
        sa.Column("raw", sa.String(500)),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="SET NULL")),
        sa.Column("state", sa.String(16), nullable=False),
        sa.Column("attendance_id", sa.Integer,
                  sa.ForeignKey("attendance.id", ondelete="SET NULL")),
        sa.Column("error", sa.String(255)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("applied_at", sa.DateTime(timezone=True)),
    )
    for col in ("device_id", "import_batch", "pin", "punch_time", "user_id", "state"):
        op.create_index(f"ix_biometric_punch_{col}", "biometric_punch", [col])
    op.create_index("ix_biometric_punch_user_time", "biometric_punch",
                    ["user_id", "punch_time"])

    op.execute(
        "INSERT INTO permission (name, description) "
        f"SELECT '{_PERM}', 'Manage biometric devices, mappings and punch imports' "
        f"FROM DUAL WHERE NOT EXISTS (SELECT 1 FROM permission WHERE name = '{_PERM}')"
    )
    op.execute(
        "INSERT IGNORE INTO role_permissions (role_id, permission_id) "
        "SELECT r.id, p.id FROM role r, permission p "
        f"WHERE r.name IN {_ROLES} AND p.name = '{_PERM}'"
    )


def downgrade():
    op.execute(
        "DELETE rp FROM role_permissions rp "
        "JOIN permission p ON p.id = rp.permission_id "
        f"WHERE p.name = '{_PERM}'"
    )
    op.execute(f"DELETE FROM permission WHERE name = '{_PERM}'")
    op.drop_table("biometric_punch")
    op.drop_table("biometric_user_map")
    op.drop_table("biometric_device_user")
    op.drop_table("biometric_device")
