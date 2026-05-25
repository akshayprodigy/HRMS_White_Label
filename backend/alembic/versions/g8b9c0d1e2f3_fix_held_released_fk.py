"""fix held_released_in_run_id FK to SET NULL on delete

Revision ID: g8b9c0d1e2f3
Revises: f7a8b9c0d1e2
Create Date: 2026-03-27

"""
from alembic import op

revision = "g8b9c0d1e2f3"
down_revision = "f7a8b9c0d1e2"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # MariaDB: drop old FK, add new one with ON DELETE SET NULL
    op.drop_constraint(
        "payrollline_ibfk_3", "payrollline", type_="foreignkey"
    )
    op.create_foreign_key(
        "payrollline_ibfk_held_run",
        "payrollline",
        "payrollrun",
        ["held_released_in_run_id"],
        ["id"],
        ondelete="SET NULL",
    )


def downgrade() -> None:
    op.drop_constraint(
        "payrollline_ibfk_held_run", "payrollline", type_="foreignkey"
    )
    op.create_foreign_key(
        "payrollline_ibfk_3",
        "payrollline",
        "payrollrun",
        ["held_released_in_run_id"],
        ["id"],
    )
