"""add_predicted_behavior_to_telemetry

Revision ID: 2082c4e4b0dc
Revises: 9c312871348b
Create Date: 2026-08-17 15:17:36.637502

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2082c4e4b0dc'
down_revision: Union[str, None] = '9c312871348b'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "telemetry",
        sa.Column("predicted_behavior", sa.String(), nullable=True)
    )
    op.add_column(
        "telemetry",
        sa.Column("behavior_confidence", sa.Float(), nullable=True)
    )


def downgrade() -> None:
    op.drop_column("telemetry", "behavior_confidence")
    op.drop_column("telemetry", "predicted_behavior")
