"""add quotation versions

Revision ID: b7d1e0c4f2a9
Revises: a3c2f9b1d4e7
Create Date: 2026-03-10 10:05:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'b7d1e0c4f2a9'
down_revision: Union[str, None] = 'a3c2f9b1d4e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'quotationversion',
        sa.Column('id', sa.Integer(), nullable=False),
        sa.Column('estimate_version_id', sa.Integer(), nullable=False),
        sa.Column('version_number', sa.Integer(), nullable=False),
        sa.Column('status', sa.String(length=20), nullable=False),
        sa.Column('filename', sa.String(length=255), nullable=False),
        sa.Column('mime_type', sa.String(length=80), nullable=False),
        sa.Column('sha256', sa.String(length=64), nullable=False),
        sa.Column('snapshot_data', sa.JSON(), nullable=False),
        sa.Column('pdf_data', sa.LargeBinary(), nullable=False),
        sa.Column('created_by_id', sa.Integer(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ['estimate_version_id'],
            ['estimateversion.id'],
            ondelete='CASCADE',
        ),
        sa.ForeignKeyConstraint(['created_by_id'], ['user.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint(
            'estimate_version_id',
            'version_number',
            name='uq_quotationversion_estimate_version_id_version_number',
        ),
    )
    op.create_index(
        op.f('ix_quotationversion_id'),
        'quotationversion',
        ['id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_quotationversion_estimate_version_id'),
        'quotationversion',
        ['estimate_version_id'],
        unique=False,
    )
    op.create_index(
        op.f('ix_quotationversion_sha256'),
        'quotationversion',
        ['sha256'],
        unique=False,
    )
    op.create_index(
        op.f('ix_quotationversion_created_by_id'),
        'quotationversion',
        ['created_by_id'],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f('ix_quotationversion_created_by_id'),
        table_name='quotationversion',
    )
    op.drop_index(
        op.f('ix_quotationversion_sha256'),
        table_name='quotationversion',
    )
    op.drop_index(
        op.f('ix_quotationversion_estimate_version_id'),
        table_name='quotationversion',
    )
    op.drop_index(
        op.f('ix_quotationversion_id'),
        table_name='quotationversion',
    )
    op.drop_table('quotationversion')
