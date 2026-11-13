"""attendance selfie + liveness + offline punch columns, attendance_selfie table

Revision ID: c7d1e4f8a2b9
Revises: b5e2c7a9d1f4
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "c7d1e4f8a2b9"
down_revision = "b5e2c7a9d1f4"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "attendance_selfie",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("filename", sa.String(255), nullable=False, unique=True),
        sa.Column("content_type", sa.String(50), nullable=False),
        sa.Column("size", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_attendance_selfie_id", "attendance_selfie", ["id"])
    op.create_index("ix_attendance_selfie_user_id", "attendance_selfie",
                    ["user_id"])
    op.add_column("attendance", sa.Column("selfie_url", sa.String(255), nullable=True))
    op.add_column("attendance", sa.Column("liveness_passed", sa.Boolean, nullable=True))
    op.add_column("attendance", sa.Column("liveness_score", sa.Float, nullable=True))
    op.add_column("attendance", sa.Column("punch_out_selfie_url", sa.String(255), nullable=True))
    op.add_column("attendance", sa.Column("punch_out_liveness_passed", sa.Boolean, nullable=True))
    op.add_column("attendance", sa.Column("punch_out_liveness_score", sa.Float, nullable=True))
    op.add_column("attendance", sa.Column(
        "is_offline", sa.Boolean, nullable=False, server_default="0"))
    op.add_column("attendance", sa.Column("client_uuid", sa.String(64), nullable=True))
    op.add_column("attendance", sa.Column("punch_out_client_uuid", sa.String(64), nullable=True))
    op.add_column("attendance", sa.Column(
        "device_captured_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("attendance", sa.Column("review_flag", sa.String(32), nullable=True))
    op.create_unique_constraint("uq_attendance_client_uuid", "attendance", ["client_uuid"])
    op.create_unique_constraint(
        "uq_attendance_punch_out_client_uuid", "attendance", ["punch_out_client_uuid"])
    op.create_index("ix_attendance_review_flag", "attendance", ["review_flag"])


def downgrade():
    op.drop_index("ix_attendance_review_flag", table_name="attendance")
    op.drop_constraint("uq_attendance_punch_out_client_uuid", "attendance", type_="unique")
    op.drop_constraint("uq_attendance_client_uuid", "attendance", type_="unique")
    for c in ("review_flag", "device_captured_at", "punch_out_client_uuid",
              "client_uuid", "is_offline", "punch_out_liveness_score",
              "punch_out_liveness_passed", "punch_out_selfie_url",
              "liveness_score", "liveness_passed", "selfie_url"):
        op.drop_column("attendance", c)
    op.drop_table("attendance_selfie")
