"""Enforce one assigned animal per physical device.

Revision ID: 1b7d9e4c5a6f
Revises: f0a6b8c3d4e5
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "1b7d9e4c5a6f"
down_revision: Union[str, None] = "f0a6b8c3d4e5"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    bind = op.get_bind()
    duplicate = bind.execute(
        sa.text(
            """
            SELECT assigned_device
            FROM animals
            WHERE assigned_device IS NOT NULL
            GROUP BY assigned_device
            HAVING COUNT(*) > 1
            LIMIT 1
            """
        )
    ).scalar()
    if duplicate:
        raise RuntimeError(
            "Cannot enforce unique animal device assignment: "
            f"device {duplicate} is assigned more than once"
        )

    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("animals")}
    if "uq_animals_assigned_device" in indexes:
        return
    if "idx_animals_device" in indexes:
        op.drop_index("idx_animals_device", table_name="animals")
    op.create_index(
        "uq_animals_assigned_device",
        "animals",
        ["assigned_device"],
        unique=True,
    )


def downgrade() -> None:
    bind = op.get_bind()
    indexes = {item["name"] for item in sa.inspect(bind).get_indexes("animals")}
    if "uq_animals_assigned_device" in indexes:
        op.drop_index("uq_animals_assigned_device", table_name="animals")
    if "idx_animals_device" not in indexes:
        op.create_index("idx_animals_device", "animals", ["assigned_device"], unique=False)
