"""reconcile required farm-scoped columns

Revision ID: d8e4f6a1b2c3
Revises: c7b2a4d9e1f0
Create Date: 2026-08-29 19:42:00.000000
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d8e4f6a1b2c3"
down_revision: Union[str, None] = "c7b2a4d9e1f0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


REQUIRED_COLUMNS = (
    ("animals", "farm_id"),
    ("alerts", "animal_id"),
    ("alerts", "type"),
    ("alerts", "severity"),
    ("geofences", "farm_id"),
)


def _assert_no_null_values() -> None:
    connection = op.get_bind()
    violations = []
    for table_name, column_name in REQUIRED_COLUMNS:
        count = connection.execute(
            sa.text(
                f'SELECT count(*) FROM "{table_name}" '
                f'WHERE "{column_name}" IS NULL'
            )
        ).scalar_one()
        if count:
            violations.append(f"{table_name}.{column_name}={count}")

    if violations:
        details = ", ".join(violations)
        raise RuntimeError(
            "Cannot apply required-column reconciliation while NULL values exist: "
            f"{details}"
        )


def upgrade() -> None:
    _assert_no_null_values()

    op.alter_column("animals", "farm_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("alerts", "animal_id", existing_type=sa.Integer(), nullable=False)
    op.alter_column("alerts", "type", existing_type=sa.String(50), nullable=False)
    op.alter_column("alerts", "severity", existing_type=sa.String(20), nullable=False)
    op.alter_column("geofences", "farm_id", existing_type=sa.Integer(), nullable=False)


def downgrade() -> None:
    op.alter_column("geofences", "farm_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("alerts", "severity", existing_type=sa.String(20), nullable=True)
    op.alter_column("alerts", "type", existing_type=sa.String(50), nullable=True)
    op.alter_column("alerts", "animal_id", existing_type=sa.Integer(), nullable=True)
    op.alter_column("animals", "farm_id", existing_type=sa.Integer(), nullable=True)
