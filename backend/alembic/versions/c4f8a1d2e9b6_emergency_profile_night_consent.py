"""emergency contacts, blood group/gender, night-shift consent, transport flag

Revision ID: c4f8a1d2e9b6
Revises: e7b1c4d9a2f3
Create Date: 2026-11-13
"""
import sqlalchemy as sa
from alembic import op

revision = "c4f8a1d2e9b6"
down_revision = "e7b1c4d9a2f3"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("employee", sa.Column("gender", sa.String(16), nullable=True))
    op.add_column("employee", sa.Column("blood_group", sa.String(4), nullable=True))
    op.add_column("roster_entry", sa.Column(
        "transport_required", sa.Boolean, nullable=False, server_default=sa.false()))
    op.create_table(
        "employee_emergency_contact",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("relation", sa.String(50), nullable=False),
        sa.Column("phone", sa.String(20), nullable=False),
        sa.Column("is_primary", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_employee_emergency_contact_id", "employee_emergency_contact", ["id"])
    op.create_index("ix_employee_emergency_contact_user_id",
                    "employee_emergency_contact", ["user_id"])
    op.create_table(
        "night_shift_consent",
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("user_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="CASCADE"), nullable=False),
        sa.Column("consent_given", sa.Boolean, nullable=False, server_default=sa.true()),
        sa.Column("valid_from", sa.Date, nullable=False),
        sa.Column("valid_to", sa.Date, nullable=True),
        sa.Column("recorded_by_id", sa.Integer,
                  sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("document_url", sa.String(500), nullable=True),
        sa.Column("note", sa.String(255), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_night_shift_consent_id", "night_shift_consent", ["id"])
    op.create_index("ix_night_shift_consent_user_id", "night_shift_consent", ["user_id"])


def downgrade():
    op.drop_table("night_shift_consent")
    op.drop_table("employee_emergency_contact")
    op.drop_column("roster_entry", "transport_required")
    op.drop_column("employee", "blood_group")
    op.drop_column("employee", "gender")
