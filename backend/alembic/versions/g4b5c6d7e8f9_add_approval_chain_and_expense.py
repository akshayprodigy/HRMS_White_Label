"""add generic approval chain + expense/travel

Pure additive — net-new domain. Legacy approval tables (approvalitem,
approvalstep) untouched.

Revision ID: g4b5c6d7e8f9
Revises: f3a4b5c6d7e8
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "g4b5c6d7e8f9"
down_revision = "f3a4b5c6d7e8"
branch_labels = None
depends_on = None


def upgrade():
    # ---------------------- approval_chain -----------------------
    op.create_table(
        "approval_chain",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("effective_from", sa.Date(), nullable=False),
        sa.Column("effective_to", sa.Date(), nullable=True),
        sa.Column("auto_approve_below_paise", sa.Integer(), nullable=True),
        sa.Column("skip_if_same_person", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint(
            "name", "entity_type",
            name="uq_approval_chain_name_entity",
        ),
    )
    op.create_index(
        "ix_approval_chain_entity_type", "approval_chain", ["entity_type"]
    )
    op.create_index(
        "ix_approval_chain_department", "approval_chain", ["department"]
    )
    op.create_index(
        "ix_approval_chain_is_active", "approval_chain", ["is_active"]
    )

    # -------------------- approval_chain_step --------------------
    op.create_table(
        "approval_chain_step",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chain_id", sa.Integer(),
            sa.ForeignKey("approval_chain.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("approver_type", sa.String(32), nullable=False),
        sa.Column("approver_ref", sa.String(120), nullable=True),
        sa.Column("mode", sa.String(16),
                  nullable=False, server_default="sequential"),
        sa.Column("parallel_rule", sa.String(8),
                  nullable=False, server_default="all"),
        sa.Column("min_amount_paise", sa.Integer(), nullable=True),
        sa.Column("max_amount_paise", sa.Integer(), nullable=True),
        sa.Column("skip_if_same_person", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("skip_if_absent_days", sa.Integer(), nullable=True),
        sa.Column("label", sa.String(120), nullable=True),
        sa.UniqueConstraint(
            "chain_id", "step_order",
            name="uq_chain_step_order",
        ),
    )
    op.create_index(
        "ix_approval_chain_step_chain_id",
        "approval_chain_step", ["chain_id"],
    )

    # ------------------ chained_approval_instance ----------------
    op.create_table(
        "chained_approval_instance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "chain_id", sa.Integer(),
            sa.ForeignKey("approval_chain.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("entity_type", sa.String(32), nullable=False),
        sa.Column("entity_id", sa.Integer(), nullable=False),
        sa.Column(
            "submitter_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount_paise", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("context_json", sa.JSON(),
                  nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(16),
                  nullable=False, server_default="pending"),
        sa.Column("current_step_order", sa.Integer(),
                  nullable=False, server_default="1"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("finalized_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_chained_approval_instance_entity",
        "chained_approval_instance",
        ["entity_type", "entity_id"],
    )
    op.create_index(
        "ix_chained_approval_instance_status",
        "chained_approval_instance", ["status"],
    )
    op.create_index(
        "ix_chained_approval_instance_submitter_id",
        "chained_approval_instance", ["submitter_id"],
    )

    # ----------------- chained_approval_step_instance -----------
    op.create_table(
        "chained_approval_step_instance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instance_id", sa.Integer(),
            sa.ForeignKey(
                "chained_approval_instance.id", ondelete="CASCADE"
            ),
            nullable=False,
        ),
        sa.Column("step_order", sa.Integer(), nullable=False),
        sa.Column("approver_type", sa.String(32), nullable=False),
        sa.Column(
            "approver_user_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("parallel_rule", sa.String(8), nullable=False),
        sa.Column("status", sa.String(16),
                  nullable=False, server_default="pending"),
        sa.Column("comment", sa.String(500), nullable=True),
        sa.Column("actioned_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("label", sa.String(120), nullable=True),
    )
    op.create_index(
        "ix_chained_step_instance_instance_id",
        "chained_approval_step_instance", ["instance_id"],
    )
    op.create_index(
        "ix_chained_step_instance_approver",
        "chained_approval_step_instance", ["approver_user_id"],
    )
    op.create_index(
        "ix_chained_step_instance_status",
        "chained_approval_step_instance", ["status"],
    )

    # ---------------------- expense_category --------------------
    op.create_table(
        "expense_category",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(80), nullable=False, unique=True),
        sa.Column("code", sa.String(20), nullable=True, unique=True),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("per_diem_cap_paise", sa.Integer(), nullable=True),
        sa.Column("receipt_required_above_paise",
                  sa.Integer(), nullable=True),
        sa.Column("policy_mode", sa.String(8),
                  nullable=False, server_default="warn"),
        sa.Column("notes", sa.Text(), nullable=True),
    )

    # ---------------------- travel_request ----------------------
    op.create_table(
        "travel_request",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "submitter_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("purpose", sa.String(240), nullable=False),
        sa.Column("from_city", sa.String(120), nullable=False),
        sa.Column("to_city", sa.String(120), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("estimated_cost_paise", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("advance_requested_paise", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("advance_paid_paise", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("status", sa.String(16),
                  nullable=False, server_default="draft"),
        sa.Column(
            "approval_instance_id", sa.Integer(),
            sa.ForeignKey(
                "chained_approval_instance.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_travel_request_employee_id", "travel_request", ["employee_id"]
    )
    op.create_index(
        "ix_travel_request_status", "travel_request", ["status"]
    )

    # ---------------------- expense_claim ------------------------
    op.create_table(
        "expense_claim",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("employee.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "submitter_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("title", sa.String(200), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("claim_date", sa.Date(), nullable=False),
        sa.Column(
            "project_id", sa.Integer(),
            sa.ForeignKey("project.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("cost_center", sa.String(80), nullable=True),
        sa.Column("total_amount_paise", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("status", sa.String(24),
                  nullable=False, server_default="draft"),
        sa.Column(
            "approval_instance_id", sa.Integer(),
            sa.ForeignKey(
                "chained_approval_instance.id", ondelete="SET NULL"
            ),
            nullable=True,
        ),
        sa.Column("reimbursement_mode", sa.String(16), nullable=True),
        sa.Column("reimbursed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reimbursed_reference", sa.String(120), nullable=True),
        sa.Column(
            "payroll_run_id", sa.Integer(),
            sa.ForeignKey("payrollrun.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "linked_travel_request_id", sa.Integer(),
            sa.ForeignKey("travel_request.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("policy_flags_json", sa.JSON(),
                  nullable=False, server_default=sa.text("'{}'::json")),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index(
        "ix_expense_claim_employee_id", "expense_claim", ["employee_id"]
    )
    op.create_index(
        "ix_expense_claim_status", "expense_claim", ["status"]
    )
    op.create_index(
        "ix_expense_claim_claim_date", "expense_claim", ["claim_date"]
    )
    op.create_index(
        "ix_expense_claim_payroll_run_id",
        "expense_claim", ["payroll_run_id"],
    )

    # ---------------------- expense_line_item -------------------
    op.create_table(
        "expense_line_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "claim_id", sa.Integer(),
            sa.ForeignKey("expense_claim.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "category_id", sa.Integer(),
            sa.ForeignKey("expense_category.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("amount_paise", sa.Integer(),
                  nullable=False, server_default="0"),
        sa.Column("line_date", sa.Date(), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("receipt_url", sa.String(500), nullable=True),
        sa.Column("is_out_of_policy", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("policy_flag_reason", sa.String(240), nullable=True),
    )
    op.create_index(
        "ix_expense_line_item_claim_id", "expense_line_item", ["claim_id"]
    )


def downgrade():
    op.drop_index("ix_expense_line_item_claim_id",
                  table_name="expense_line_item")
    op.drop_table("expense_line_item")

    for idx in (
        "ix_expense_claim_payroll_run_id",
        "ix_expense_claim_claim_date",
        "ix_expense_claim_status",
        "ix_expense_claim_employee_id",
    ):
        op.drop_index(idx, table_name="expense_claim")
    op.drop_table("expense_claim")

    for idx in (
        "ix_travel_request_status",
        "ix_travel_request_employee_id",
    ):
        op.drop_index(idx, table_name="travel_request")
    op.drop_table("travel_request")

    op.drop_table("expense_category")

    for idx in (
        "ix_chained_step_instance_status",
        "ix_chained_step_instance_approver",
        "ix_chained_step_instance_instance_id",
    ):
        op.drop_index(idx, table_name="chained_approval_step_instance")
    op.drop_table("chained_approval_step_instance")

    for idx in (
        "ix_chained_approval_instance_submitter_id",
        "ix_chained_approval_instance_status",
        "ix_chained_approval_instance_entity",
    ):
        op.drop_index(idx, table_name="chained_approval_instance")
    op.drop_table("chained_approval_instance")

    op.drop_index("ix_approval_chain_step_chain_id",
                  table_name="approval_chain_step")
    op.drop_table("approval_chain_step")

    for idx in (
        "ix_approval_chain_is_active",
        "ix_approval_chain_department",
        "ix_approval_chain_entity_type",
    ):
        op.drop_index(idx, table_name="approval_chain")
    op.drop_table("approval_chain")
