"""set default currency INR

Revision ID: 3f1c2a9d8b77
Revises: 1a7c2c9e3c10
Create Date: 2026-03-12

"""

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "3f1c2a9d8b77"
down_revision: Union[str, None] = "1a7c2c9e3c10"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "UPDATE estimateversion SET currency='INR' WHERE currency='USD'"
    )
    op.execute(
        "UPDATE lead_bid_task_review SET currency='INR' WHERE currency='USD'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE estimateversion SET currency='USD' WHERE currency='INR'"
    )
    op.execute(
        "UPDATE lead_bid_task_review SET currency='USD' WHERE currency='INR'"
    )
