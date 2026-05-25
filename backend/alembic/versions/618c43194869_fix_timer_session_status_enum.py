"""fix timer_session status enum

Revision ID: 618c43194869
Revises: 2d5a9455d95c
Create Date: 2026-02-22 07:35:20.306518

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '618c43194869'
down_revision: Union[str, None] = '2d5a9455d95c'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # SQLAlchemy's Enum(TimerStatus) persists Enum *names* by default
    # (RUNNING/PAUSED/STOPPED), not the `.value` strings
    # (running/paused/stopped).
    op.execute(
        "UPDATE timer_session SET status='RUNNING' WHERE status='running'"
    )
    op.execute(
        "UPDATE timer_session SET status='PAUSED' WHERE status='paused'"
    )
    op.execute(
        "UPDATE timer_session SET status='STOPPED' WHERE status='stopped'"
    )
    op.execute(
        "ALTER TABLE timer_session "
        "MODIFY status ENUM('RUNNING','PAUSED','STOPPED') "
        "NOT NULL DEFAULT 'RUNNING'"
    )


def downgrade() -> None:
    op.execute(
        "UPDATE timer_session SET status='running' WHERE status='RUNNING'"
    )
    op.execute(
        "UPDATE timer_session SET status='paused' WHERE status='PAUSED'"
    )
    op.execute(
        "UPDATE timer_session SET status='stopped' WHERE status='STOPPED'"
    )
    op.execute(
        "ALTER TABLE timer_session "
        "MODIFY status ENUM('running','paused','stopped') "
        "NOT NULL DEFAULT 'running'"
    )
