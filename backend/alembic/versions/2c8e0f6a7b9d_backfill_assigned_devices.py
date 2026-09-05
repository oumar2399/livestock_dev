"""Backfill device rows for existing animal assignments.

Revision ID: 2c8e0f6a7b9d
Revises: 1b7d9e4c5a6f
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "2c8e0f6a7b9d"
down_revision: Union[str, None] = "1b7d9e4c5a6f"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    mismatch = bind.execute(
        sa.text(
            """
            SELECT a.assigned_device
            FROM animals AS a
            JOIN devices AS d ON d.id = a.assigned_device
            WHERE a.assigned_device IS NOT NULL
              AND d.farm_id IS DISTINCT FROM a.farm_id
            LIMIT 1
            """
        )
    ).scalar()
    if mismatch:
        raise RuntimeError(
            "Cannot reconcile assigned devices automatically: "
            f"device {mismatch} belongs to a different farm"
        )

    bind.execute(
        sa.text(
            """
            INSERT INTO devices (id, farm_id, model, status, created_at)
            SELECT
                a.assigned_device,
                a.farm_id,
                'M5Stack M5GO',
                'active',
                CURRENT_TIMESTAMP
            FROM animals AS a
            LEFT JOIN devices AS d ON d.id = a.assigned_device
            WHERE a.assigned_device IS NOT NULL
              AND d.id IS NULL
            """
        )
    )


def downgrade() -> None:
    # Device rows are retained because they may have received telemetry since upgrade.
    pass
