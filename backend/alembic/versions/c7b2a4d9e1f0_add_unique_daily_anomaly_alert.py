"""add unique daily anomaly alert index

Revision ID: c7b2a4d9e1f0
Revises: b4e8f1a2c3d4
"""

from typing import Sequence, Union

from alembic import op


revision: str = "c7b2a4d9e1f0"
down_revision: Union[str, None] = "b4e8f1a2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS uq_alerts_animal_type_target_date
        ON alerts (animal_id, type, (alert_metadata->>'target_date'))
        WHERE alert_metadata ? 'target_date'
        """
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS uq_alerts_animal_type_target_date")
