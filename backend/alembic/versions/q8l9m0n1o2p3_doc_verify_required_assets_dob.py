"""document verification, required document types, employee assets, dob

Adds:
- employeedocument.verified_at / verified_by_id / rejection_reason
- user.date_of_birth
- required_document_type table (pre-seeded with KYC/Education/Experience)
- employee_asset table

Revision ID: q8l9m0n1o2p3
Revises: p7k8l9m0n1o2
Create Date: 2026-04-29
"""
from alembic import op
import sqlalchemy as sa

revision = "q8l9m0n1o2p3"
down_revision = "p7k8l9m0n1o2"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Document verification metadata
    op.add_column(
        "employeedocument",
        sa.Column("verified_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "employeedocument",
        sa.Column(
            "verified_by_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "employeedocument",
        sa.Column("rejection_reason", sa.Text(), nullable=True),
    )

    # 2. User date of birth
    op.add_column("user", sa.Column("date_of_birth", sa.Date(), nullable=True))

    # 3. Admin-managed list of required document types
    op.create_table(
        "required_document_type",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("doc_type", sa.String(50), nullable=False, unique=True),
        sa.Column("description", sa.String(500), nullable=True),
        sa.Column(
            "is_active", sa.Boolean(), nullable=False, server_default=sa.text("1")
        ),
    )
    # Sensible defaults so the feature is useful immediately.
    op.execute(
        "INSERT INTO required_document_type (doc_type, description, is_active) VALUES "
        "('KYC', 'Aadhaar / PAN / passport copy', 1), "
        "('Education', 'Highest degree certificate', 1), "
        "('Experience', 'Relieving / experience letters from prior employers', 1)"
    )

    # 4. Employee assets (replaces the hardcoded mock data in the UI)
    op.create_table(
        "employee_asset",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id",
            sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
            index=True,
        ),
        sa.Column("asset_type", sa.String(50), nullable=False),
        sa.Column("model", sa.String(150), nullable=False),
        sa.Column("identifier", sa.String(100), nullable=True),
        sa.Column("serial_no", sa.String(100), nullable=True),
        sa.Column("issued_date", sa.Date(), nullable=True),
        sa.Column("returned_date", sa.Date(), nullable=True),
        sa.Column(
            "status", sa.String(30), nullable=False, server_default="allocated"
        ),
        sa.Column("condition", sa.String(50), nullable=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "created_by_id",
            sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )


def downgrade():
    op.drop_table("employee_asset")
    op.drop_table("required_document_type")
    op.drop_column("user", "date_of_birth")
    op.drop_column("employeedocument", "rejection_reason")
    op.drop_column("employeedocument", "verified_by_id")
    op.drop_column("employeedocument", "verified_at")
