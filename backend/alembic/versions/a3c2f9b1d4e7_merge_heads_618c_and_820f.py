"""merge heads 618c43194869 and 820fe877db81

Revision ID: a3c2f9b1d4e7
Revises: 618c43194869, 820fe877db81
Create Date: 2026-03-10 10:00:00.000000

"""

from typing import Sequence, Union


# revision identifiers, used by Alembic.
revision: str = 'a3c2f9b1d4e7'
down_revision: Union[str, Sequence[str], None] = (
    '618c43194869',
    '820fe877db81',
)
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # This is a merge revision to resolve multiple Alembic heads.
    # No schema changes are required.
    pass


def downgrade() -> None:
    # This is a merge revision to resolve multiple Alembic heads.
    # No schema changes are required.
    pass
