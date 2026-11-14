"""biometric_punch composite indexes (state, punch_time) and (device_id, punch_time)

Roadmap v2 Phase 4, final review.

Revision ID: c4e8a2f6b1d9
Revises: b3f7d1a9c5e2
Create Date: 2026-11-14
"""
from alembic import op

revision = "c4e8a2f6b1d9"
down_revision = "b3f7d1a9c5e2"
branch_labels = None
depends_on = None


def upgrade():
    op.create_index("ix_biometric_punch_state_time", "biometric_punch",
                    ["state", "punch_time"])
    op.create_index("ix_biometric_punch_device_time", "biometric_punch",
                    ["device_id", "punch_time"])


def downgrade():
    # device_id keeps its own single-column index (backs the FK), so dropping
    # the composites is safe.
    op.drop_index("ix_biometric_punch_device_time", table_name="biometric_punch")
    op.drop_index("ix_biometric_punch_state_time", table_name="biometric_punch")
