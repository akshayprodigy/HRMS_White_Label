"""add exit management tables

Revision ID: d5e6f7a8b9c0
Revises: c4d5e6f7a8b9
Create Date: 2026-03-26

"""
from alembic import op
import sqlalchemy as sa

# revision identifiers, used by Alembic.
revision = "d5e6f7a8b9c0"
down_revision = "c4d5e6f7a8b9"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Add notice_period_days to employee
    op.add_column(
        "employee",
        sa.Column("notice_period_days", sa.Integer(), nullable=True, server_default="30"),
    )

    # Resignation table
    op.create_table(
        "resignation",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id", ondelete="CASCADE"), unique=True, index=True, nullable=False),
        sa.Column("reason", sa.String(50), nullable=False),
        sa.Column("reason_details", sa.Text(), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="submitted", index=True),
        sa.Column("resignation_date", sa.Date(), nullable=False),
        sa.Column("last_working_day", sa.Date(), nullable=False),
        sa.Column("notice_period_days", sa.Integer(), nullable=False),
        sa.Column("accepted_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("released_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("withdrawn_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Exit Interview table
    op.create_table(
        "exitinterview",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("resignation_id", sa.Integer(), sa.ForeignKey("resignation.id", ondelete="CASCADE"), unique=True, index=True, nullable=False),
        sa.Column("employee_id", sa.Integer(), sa.ForeignKey("employee.id", ondelete="CASCADE"), index=True, nullable=False),
        # Reason checkboxes
        sa.Column("reason_career", sa.Boolean(), server_default="0"),
        sa.Column("reason_studies", sa.Boolean(), server_default="0"),
        sa.Column("reason_personal", sa.Boolean(), server_default="0"),
        sa.Column("reason_relocation", sa.Boolean(), server_default="0"),
        sa.Column("reason_health", sa.Boolean(), server_default="0"),
        sa.Column("reason_work_environment", sa.Boolean(), server_default="0"),
        sa.Column("reason_compensation", sa.Boolean(), server_default="0"),
        sa.Column("reason_relationship", sa.Boolean(), server_default="0"),
        sa.Column("reason_role_mismatch", sa.Boolean(), server_default="0"),
        sa.Column("reason_other", sa.String(255), nullable=True),
        sa.Column("reason_explanation", sa.Text(), nullable=True),
        # Ratings
        sa.Column("rating_job_satisfaction", sa.Integer(), nullable=True),
        sa.Column("rating_work_life_balance", sa.Integer(), nullable=True),
        sa.Column("rating_team_cooperation", sa.Integer(), nullable=True),
        sa.Column("rating_management_communication", sa.Integer(), nullable=True),
        sa.Column("rating_training_development", sa.Integer(), nullable=True),
        sa.Column("rating_career_growth", sa.Integer(), nullable=True),
        sa.Column("rating_compensation", sa.Integer(), nullable=True),
        sa.Column("rating_company_culture", sa.Integer(), nullable=True),
        # Open feedback
        sa.Column("feedback_liked_most", sa.Text(), nullable=True),
        sa.Column("feedback_liked_least", sa.Text(), nullable=True),
        sa.Column("feedback_suggestions", sa.Text(), nullable=True),
        # HR
        sa.Column("hr_remarks", sa.Text(), nullable=True),
        sa.Column("hr_reviewed_by_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="SET NULL"), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Clearance Request table
    op.create_table(
        "clearancerequest",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("resignation_id", sa.Integer(), sa.ForeignKey("resignation.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("department", sa.String(100), nullable=False),
        sa.Column("assigned_to_id", sa.Integer(), sa.ForeignKey("user.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("status", sa.String(20), server_default="pending", index=True),
        sa.Column("remarks", sa.Text(), nullable=True),
        sa.Column("cleared_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now()),
    )

    # Clearance Item table
    op.create_table(
        "clearanceitem",
        sa.Column("id", sa.Integer(), primary_key=True, index=True),
        sa.Column("clearance_request_id", sa.Integer(), sa.ForeignKey("clearancerequest.id", ondelete="CASCADE"), index=True, nullable=False),
        sa.Column("item_name", sa.String(255), nullable=False),
        sa.Column("is_cleared", sa.Boolean(), server_default="0"),
        sa.Column("remarks", sa.String(500), nullable=True),
    )


def downgrade() -> None:
    op.drop_table("clearanceitem")
    op.drop_table("clearancerequest")
    op.drop_table("exitinterview")
    op.drop_table("resignation")
    op.drop_column("employee", "notice_period_days")
