"""add_accel_3axes_windowing

Revision ID: 9c312871348b
Revises: fbc3952585f9
Create Date: 2026-04-12 11:21:25.018765

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '9c312871348b'
down_revision: Union[str, None] = 'fbc3952585f9'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
