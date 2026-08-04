"""per-employment-type leave policy (W1)

Join table gating leave eligibility + quota per (employment_type, leave_type).
Seeds one row per pair: contractual/advisor types are eligible only for unpaid
leave; all other types eligible for everything. A MISSING row = eligible
(fallback), so this seed is a policy default, not a hard requirement.

Revision ID: t8u9v0w1x2y3
Revises: s7t8u9v0w1x2
Create Date: 2026-08-04
"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy import table, column, select

revision = "t8u9v0w1x2y3"
down_revision = "s7t8u9v0w1x2"
branch_labels = None
depends_on = None

NON_STATUTORY = ("contractual", "advisor")


def upgrade():
    op.create_table(
        "employment_type_leave_policy",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("employment_type_id", sa.Integer(), nullable=False),
        sa.Column("leave_type_id", sa.Integer(), nullable=False),
        sa.Column("is_eligible", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("annual_quota", sa.Float(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now(), server_onupdate=sa.func.now()),
        sa.UniqueConstraint("employment_type_id", "leave_type_id", name="uq_emptype_leavetype"),
        sa.ForeignKeyConstraint(["employment_type_id"], ["employment_type.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["leave_type_id"], ["leavetype.id"], ondelete="CASCADE"),
    )
    op.create_index("ix_emptype_leave_policy_et", "employment_type_leave_policy", ["employment_type_id"], unique=False)
    op.create_index("ix_emptype_leave_policy_lt", "employment_type_leave_policy", ["leave_type_id"], unique=False)

    # Seed the matrix: contractual/advisor eligible only for unpaid leave.
    conn = op.get_bind()
    et = table("employment_type", column("id", sa.Integer), column("code", sa.String))
    lt = table("leavetype", column("id", sa.Integer), column("unpaid_allowed", sa.Boolean))
    ets = conn.execute(select(et.c.id, et.c.code)).fetchall()
    lts = conn.execute(select(lt.c.id, lt.c.unpaid_allowed)).fetchall()
    policy = table(
        "employment_type_leave_policy",
        column("employment_type_id", sa.Integer),
        column("leave_type_id", sa.Integer),
        column("is_eligible", sa.Boolean),
    )
    rows = []
    for et_id, code in ets:
        non_statutory = (code or "").lower() in NON_STATUTORY
        for lt_id, unpaid in lts:
            eligible = True if not non_statutory else bool(unpaid)
            rows.append({"employment_type_id": et_id, "leave_type_id": lt_id, "is_eligible": eligible})
    if rows:
        op.bulk_insert(policy, rows)


def downgrade():
    op.drop_index("ix_emptype_leave_policy_lt", table_name="employment_type_leave_policy")
    op.drop_index("ix_emptype_leave_policy_et", table_name="employment_type_leave_policy")
    op.drop_table("employment_type_leave_policy")
