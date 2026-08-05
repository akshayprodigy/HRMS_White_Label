"""multi-stage salary revision (W11)

Adds the multi-stage columns to salary_revision and seeds a generic approval
chain for entity_type='salary_revision' (single CEO sign-off step; HR can add
an MD step or swap the approver in the Chain Builder).

Revision ID: v0w1x2y3z4a5
Revises: u9v0w1x2y3z4
Create Date: 2026-08-05
"""
from alembic import op
import sqlalchemy as sa

revision = "v0w1x2y3z4a5"
down_revision = "u9v0w1x2y3z4"
branch_labels = None
depends_on = None

CHAIN_NAME = "Salary Revision — CEO sign-off"


def upgrade():
    op.add_column("salary_revision", sa.Column("is_multistage", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("salary_revision", sa.Column("chain_instance_id", sa.Integer(), nullable=True))
    op.add_column("salary_revision", sa.Column("value_authored_by_id", sa.Integer(), nullable=True))
    op.add_column("salary_revision", sa.Column("value_authored_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_salary_revision_is_multistage", "salary_revision", ["is_multistage"], unique=False)
    op.create_foreign_key(
        "fk_salary_revision_chain_instance", "salary_revision",
        "chained_approval_instance", ["chain_instance_id"], ["id"], ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_salary_revision_value_author", "salary_revision",
        "user", ["value_authored_by_id"], ["id"], ondelete="SET NULL",
    )

    # Seed the approval chain (idempotent-ish: only if none exists for the type).
    op.execute(
        f"""
        INSERT INTO approval_chain (name, entity_type, is_active, skip_if_same_person, effective_from)
        SELECT '{CHAIN_NAME}', 'salary_revision', 1, 1, '2000-01-01' FROM DUAL
        WHERE NOT EXISTS (
            SELECT 1 FROM approval_chain WHERE entity_type = 'salary_revision'
        );
        """
    )
    op.execute(
        """
        INSERT INTO approval_chain_step (chain_id, step_order, approver_type, mode, parallel_rule)
        SELECT c.id, 1, 'ceo', 'sequential', 'all'
        FROM approval_chain c
        WHERE c.entity_type = 'salary_revision'
          AND NOT EXISTS (
            SELECT 1 FROM approval_chain_step s WHERE s.chain_id = c.id
          );
        """
    )


def downgrade():
    op.execute(
        "DELETE s FROM approval_chain_step s JOIN approval_chain c ON s.chain_id = c.id "
        "WHERE c.entity_type = 'salary_revision';"
    )
    op.execute("DELETE FROM approval_chain WHERE entity_type = 'salary_revision';")
    op.drop_constraint("fk_salary_revision_value_author", "salary_revision", type_="foreignkey")
    op.drop_constraint("fk_salary_revision_chain_instance", "salary_revision", type_="foreignkey")
    op.drop_index("ix_salary_revision_is_multistage", table_name="salary_revision")
    op.drop_column("salary_revision", "value_authored_at")
    op.drop_column("salary_revision", "value_authored_by_id")
    op.drop_column("salary_revision", "chain_instance_id")
    op.drop_column("salary_revision", "is_multistage")
