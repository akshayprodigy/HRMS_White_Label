"""add role to bid task review lines

Revision ID: 1a7c2c9e3c10
Revises: 17441bc84e66
Create Date: 2026-03-12

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "1a7c2c9e3c10"
down_revision: Union[str, None] = "17441bc84e66"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "lead_bid_task_review_line",
        sa.Column("role", sa.String(length=100), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("lead_bid_task_review_line", "role")
