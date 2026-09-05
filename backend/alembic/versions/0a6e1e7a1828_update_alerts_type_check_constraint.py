"""update_alerts_type_check_constraint

Revision ID: 0a6e1e7a1828
Revises: 187d38a14511
Create Date: 2026-08-19 22:30:35.162142

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0a6e1e7a1828'
down_revision: Union[str, None] = '187d38a14511'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
