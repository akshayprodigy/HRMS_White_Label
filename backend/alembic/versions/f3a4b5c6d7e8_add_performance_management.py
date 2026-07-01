"""add performance management (goals, reviews, calibration, 1:1s)

Pure additive — net-new domain, no existing column touched.

Revision ID: f3a4b5c6d7e8
Revises: e2z3a4b5c6d7
Create Date: 2026-07-01
"""
from alembic import op
import sqlalchemy as sa


revision = "f3a4b5c6d7e8"
down_revision = "e2z3a4b5c6d7"
branch_labels = None
depends_on = None


def upgrade():
    # ----- review_cycle (created FIRST because Goal FK-refs it) -----
    op.create_table(
        "review_cycle",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("cycle_type", sa.String(16),
                  nullable=False, server_default="annual"),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("phases_json", sa.JSON(), nullable=False,
                  server_default=sa.text("'{}'::json")),
        sa.Column("population_json", sa.JSON(), nullable=False,
                  server_default=sa.text("'{}'::json")),
        sa.Column("status", sa.String(16),
                  nullable=False, server_default="draft"),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.UniqueConstraint("name", name="uq_review_cycle_name"),
    )
    op.create_index("ix_review_cycle_status", "review_cycle", ["status"])

    # ----- goal -----
    op.create_table(
        "goal",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "owner_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("goal_type", sa.String(16),
                  nullable=False, server_default="okr"),
        sa.Column(
            "parent_goal_id", sa.Integer(),
            sa.ForeignKey("goal.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("weight", sa.Float(),
                  nullable=False, server_default=sa.text("0.0")),
        sa.Column("target", sa.String(255), nullable=True),
        sa.Column("unit", sa.String(60), nullable=True),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("due_date", sa.Date(), nullable=False),
        sa.Column(
            "cycle_id", sa.Integer(),
            sa.ForeignKey("review_cycle.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("status", sa.String(16),
                  nullable=False, server_default="draft"),
        sa.Column("latest_progress", sa.Float(),
                  nullable=False, server_default=sa.text("0.0")),
        sa.Column("latest_confidence", sa.String(8), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_goal_owner", "goal", ["owner_id"])
    op.create_index("ix_goal_parent", "goal", ["parent_goal_id"])
    op.create_index("ix_goal_cycle", "goal", ["cycle_id"])
    op.create_index("ix_goal_status", "goal", ["status"])
    op.create_index("ix_goal_type", "goal", ["goal_type"])

    # ----- key_result -----
    op.create_table(
        "key_result",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "goal_id", sa.Integer(),
            sa.ForeignKey("goal.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("target", sa.String(120), nullable=True),
        sa.Column("unit", sa.String(60), nullable=True),
        sa.Column("weight", sa.Float(),
                  nullable=False, server_default=sa.text("0.0")),
        sa.Column("progress_percent", sa.Float(),
                  nullable=False, server_default=sa.text("0.0")),
        sa.Column("status", sa.String(16),
                  nullable=False, server_default="active"),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_kr_goal", "key_result", ["goal_id"])

    # ----- goal_check_in -----
    op.create_table(
        "goal_check_in",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "goal_id", sa.Integer(),
            sa.ForeignKey("goal.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("progress_percent", sa.Float(),
                  nullable=False, server_default=sa.text("0.0")),
        sa.Column("confidence", sa.String(8),
                  nullable=False, server_default="green"),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column(
            "created_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.create_index("ix_checkin_goal", "goal_check_in", ["goal_id"])
    op.create_index("ix_checkin_created_at", "goal_check_in", ["created_at"])

    # ----- review_form -----
    op.create_table(
        "review_form",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(160), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scale_json", sa.JSON(), nullable=False,
                  server_default=sa.text("'{}'::json")),
        sa.Column("is_active", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("name", name="uq_review_form_name"),
    )

    # ----- review_section -----
    op.create_table(
        "review_section",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "form_id", sa.Integer(),
            sa.ForeignKey("review_form.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("sequence", sa.Integer(),
                  nullable=False, server_default=sa.text("0")),
        sa.Column("weight", sa.Float(),
                  nullable=False, server_default=sa.text("0.0")),
    )
    op.create_index("ix_section_form", "review_section", ["form_id"])

    # ----- review_question -----
    op.create_table(
        "review_question",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "section_id", sa.Integer(),
            sa.ForeignKey("review_section.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(),
                  nullable=False, server_default=sa.text("0")),
        sa.Column("question_type", sa.String(20),
                  nullable=False, server_default="rating"),
        sa.Column("weight_within_section", sa.Float(),
                  nullable=False, server_default=sa.text("1.0")),
        sa.Column("scale_json", sa.JSON(), nullable=True),
        sa.Column("is_required", sa.Boolean(),
                  nullable=False, server_default=sa.true()),
    )
    op.create_index("ix_question_section", "review_question", ["section_id"])

    # ----- review_template_assignment -----
    op.create_table(
        "review_template_assignment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cycle_id", sa.Integer(),
            sa.ForeignKey("review_cycle.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "form_id", sa.Integer(),
            sa.ForeignKey("review_form.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("filter_json", sa.JSON(), nullable=False,
                  server_default=sa.text("'{}'::json")),
        sa.Column("priority", sa.Integer(),
                  nullable=False, server_default=sa.text("0")),
    )
    op.create_index("ix_tpl_asgn_cycle", "review_template_assignment", ["cycle_id"])
    op.create_index("ix_tpl_asgn_form", "review_template_assignment", ["form_id"])

    # ----- review_instance -----
    op.create_table(
        "review_instance",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cycle_id", sa.Integer(),
            sa.ForeignKey("review_cycle.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "employee_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "manager_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "skip_level_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "form_id", sa.Integer(),
            sa.ForeignKey("review_form.id", ondelete="RESTRICT"),
            nullable=False,
        ),
        sa.Column("current_phase", sa.String(20),
                  nullable=False, server_default="not_started"),
        sa.Column("self_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("manager_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("skip_level_submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("calibration_done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_released", sa.Boolean(),
                  nullable=False, server_default=sa.false()),
        sa.Column("released_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("computed_overall_rating", sa.Float(), nullable=True),
        sa.Column("manager_override_rating", sa.Float(), nullable=True),
        sa.Column("manager_override_reason", sa.String(500), nullable=True),
        sa.Column("calibrated_rating", sa.Float(), nullable=True),
        sa.Column("final_rating", sa.Float(), nullable=True),
        sa.Column(
            "approval_item_id", sa.Integer(),
            sa.ForeignKey("approvalitem.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("cycle_id", "employee_id", name="uq_review_cycle_emp"),
    )
    op.create_index("ix_instance_cycle", "review_instance", ["cycle_id"])
    op.create_index("ix_instance_employee", "review_instance", ["employee_id"])
    op.create_index("ix_instance_manager", "review_instance", ["manager_id"])
    op.create_index("ix_instance_phase", "review_instance", ["current_phase"])
    op.create_index("ix_instance_released", "review_instance", ["is_released"])

    # ----- review_response -----
    op.create_table(
        "review_response",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "instance_id", sa.Integer(),
            sa.ForeignKey("review_instance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "question_id", sa.Integer(),
            sa.ForeignKey("review_question.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("self_rating", sa.Float(), nullable=True),
        sa.Column("self_comment", sa.Text(), nullable=True),
        sa.Column("manager_rating", sa.Float(), nullable=True),
        sa.Column("manager_comment", sa.Text(), nullable=True),
        sa.Column("skip_level_rating", sa.Float(), nullable=True),
        sa.Column("skip_level_comment", sa.Text(), nullable=True),
        sa.Column("goal_snapshot_json", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("instance_id", "question_id",
                            name="uq_review_response_iq"),
    )
    op.create_index("ix_response_instance", "review_response", ["instance_id"])
    op.create_index("ix_response_question", "review_response", ["question_id"])

    # ----- calibration_session -----
    op.create_table(
        "calibration_session",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "cycle_id", sa.Integer(),
            sa.ForeignKey("review_cycle.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("department", sa.String(100), nullable=True),
        sa.Column("name", sa.String(160), nullable=True),
        sa.Column("target_curve_json", sa.JSON(), nullable=True),
        sa.Column("status", sa.String(20),
                  nullable=False, server_default="draft"),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column(
            "facilitator_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_calibration_cycle", "calibration_session", ["cycle_id"])
    op.create_index("ix_calibration_status", "calibration_session", ["status"])

    # ----- calibration_adjustment -----
    op.create_table(
        "calibration_adjustment",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "session_id", sa.Integer(),
            sa.ForeignKey("calibration_session.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "instance_id", sa.Integer(),
            sa.ForeignKey("review_instance.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("old_rating", sa.Float(), nullable=True),
        sa.Column("new_rating", sa.Float(), nullable=False),
        sa.Column("reason", sa.String(500), nullable=False),
        sa.Column(
            "adjusted_by_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("adjusted_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_adjustment_session", "calibration_adjustment", ["session_id"])
    op.create_index("ix_adjustment_instance", "calibration_adjustment", ["instance_id"])

    # ----- one_on_one -----
    op.create_table(
        "one_on_one",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "manager_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "reportee_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("scheduled_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("cadence", sa.String(20),
                  nullable=False, server_default="once"),
        sa.Column("duration_minutes", sa.Integer(),
                  nullable=False, server_default=sa.text("30")),
        sa.Column("agenda_json", sa.JSON(), nullable=False,
                  server_default=sa.text("'[]'::json")),
        sa.Column("shared_notes", sa.Text(), nullable=True),
        sa.Column("manager_private_notes", sa.Text(), nullable=True),
        sa.Column("reportee_private_notes", sa.Text(), nullable=True),
        sa.Column("status", sa.String(20),
                  nullable=False, server_default="scheduled"),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_121_manager", "one_on_one", ["manager_id"])
    op.create_index("ix_121_reportee", "one_on_one", ["reportee_id"])
    op.create_index("ix_121_scheduled", "one_on_one", ["scheduled_at"])
    op.create_index("ix_121_status", "one_on_one", ["status"])

    # ----- one_on_one_action_item -----
    op.create_table(
        "one_on_one_action_item",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column(
            "one_on_one_id", sa.Integer(),
            sa.ForeignKey("one_on_one.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column(
            "owner_id", sa.Integer(),
            sa.ForeignKey("user.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("due_date", sa.Date(), nullable=True),
        sa.Column("status", sa.String(20),
                  nullable=False, server_default="open"),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "goal_id", sa.Integer(),
            sa.ForeignKey("goal.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("created_at", sa.DateTime(timezone=True),
                  nullable=False, server_default=sa.func.now()),
    )
    op.create_index("ix_ai_121", "one_on_one_action_item", ["one_on_one_id"])
    op.create_index("ix_ai_owner", "one_on_one_action_item", ["owner_id"])
    op.create_index("ix_ai_status", "one_on_one_action_item", ["status"])


def downgrade():
    op.drop_index("ix_ai_status", table_name="one_on_one_action_item")
    op.drop_index("ix_ai_owner", table_name="one_on_one_action_item")
    op.drop_index("ix_ai_121", table_name="one_on_one_action_item")
    op.drop_table("one_on_one_action_item")

    op.drop_index("ix_121_status", table_name="one_on_one")
    op.drop_index("ix_121_scheduled", table_name="one_on_one")
    op.drop_index("ix_121_reportee", table_name="one_on_one")
    op.drop_index("ix_121_manager", table_name="one_on_one")
    op.drop_table("one_on_one")

    op.drop_index("ix_adjustment_instance", table_name="calibration_adjustment")
    op.drop_index("ix_adjustment_session", table_name="calibration_adjustment")
    op.drop_table("calibration_adjustment")

    op.drop_index("ix_calibration_status", table_name="calibration_session")
    op.drop_index("ix_calibration_cycle", table_name="calibration_session")
    op.drop_table("calibration_session")

    op.drop_index("ix_response_question", table_name="review_response")
    op.drop_index("ix_response_instance", table_name="review_response")
    op.drop_table("review_response")

    op.drop_index("ix_instance_released", table_name="review_instance")
    op.drop_index("ix_instance_phase", table_name="review_instance")
    op.drop_index("ix_instance_manager", table_name="review_instance")
    op.drop_index("ix_instance_employee", table_name="review_instance")
    op.drop_index("ix_instance_cycle", table_name="review_instance")
    op.drop_table("review_instance")

    op.drop_index("ix_tpl_asgn_form", table_name="review_template_assignment")
    op.drop_index("ix_tpl_asgn_cycle", table_name="review_template_assignment")
    op.drop_table("review_template_assignment")

    op.drop_index("ix_question_section", table_name="review_question")
    op.drop_table("review_question")

    op.drop_index("ix_section_form", table_name="review_section")
    op.drop_table("review_section")

    op.drop_table("review_form")

    op.drop_index("ix_checkin_created_at", table_name="goal_check_in")
    op.drop_index("ix_checkin_goal", table_name="goal_check_in")
    op.drop_table("goal_check_in")

    op.drop_index("ix_kr_goal", table_name="key_result")
    op.drop_table("key_result")

    op.drop_index("ix_goal_type", table_name="goal")
    op.drop_index("ix_goal_status", table_name="goal")
    op.drop_index("ix_goal_cycle", table_name="goal")
    op.drop_index("ix_goal_parent", table_name="goal")
    op.drop_index("ix_goal_owner", table_name="goal")
    op.drop_table("goal")

    op.drop_index("ix_review_cycle_status", table_name="review_cycle")
    op.drop_table("review_cycle")
