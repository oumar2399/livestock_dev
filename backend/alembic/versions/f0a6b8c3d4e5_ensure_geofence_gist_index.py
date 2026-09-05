"""ensure geofence polygon GiST index

Revision ID: f0a6b8c3d4e5
Revises: e9f5a7b2c3d4
Create Date: 2026-09-01 11:45:00.000000
"""

from typing import Sequence, Union

from alembic import op


revision: str = "f0a6b8c3d4e5"
down_revision: Union[str, None] = "e9f5a7b2c3d4"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_geofences_polygon "
        "ON geofences USING GIST (polygon)"
    )


def downgrade() -> None:
    # The index predates this assurance migration in init.sql and existing DBs.
    pass
