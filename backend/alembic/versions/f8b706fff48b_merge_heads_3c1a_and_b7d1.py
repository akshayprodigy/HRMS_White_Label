"""merge heads 3c1a and b7d1

Revision ID: f8b706fff48b
Revises: 3c1a0c2b9f7d, b7d1e0c4f2a9
Create Date: 2026-03-11 03:04:37.261327

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f8b706fff48b'
down_revision: Union[str, None] = ('3c1a0c2b9f7d', 'b7d1e0c4f2a9')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
