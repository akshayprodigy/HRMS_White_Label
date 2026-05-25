"""add employee documents table and confirmation fields

Revision ID: n5i6j7k8l9m0
Revises: m4h5i6j7k8l9
Create Date: 2026-04-02
"""
from alembic import op
import sqlalchemy as sa

revision = "n5i6j7k8l9m0"
down_revision = "m4h5i6j7k8l9"
branch_labels = None
depends_on = None


def upgrade():
    # Employee document storage
    op.create_table(
        "employeedocument",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id", ondelete="CASCADE"), nullable=False, index=True),
        sa.Column("doc_type", sa.String(50), nullable=False),
        sa.Column("original_filename", sa.String(255), nullable=False),
        sa.Column("stored_filename", sa.String(255), nullable=False),
        sa.Column("remark", sa.Text(), nullable=True),
        sa.Column("uploaded_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("uploaded_by_id", sa.Integer(), sa.ForeignKey("user.id"), nullable=True),
    )

    # Employee confirmation / probation fields
    op.add_column("employee", sa.Column("probation_end_date", sa.Date(), nullable=True))
    op.add_column("employee", sa.Column("confirmation_date", sa.Date(), nullable=True))


def downgrade():
    op.drop_column("employee", "confirmation_date")
    op.drop_column("employee", "probation_end_date")
    op.drop_table("employeedocument")
