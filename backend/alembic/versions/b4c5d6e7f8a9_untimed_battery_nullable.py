"""Allow an unknown battery (NULL) on untimed telemetry (firmware sentinel 255).

Revision ID: b4c5d6e7f8a9
Revises: a3b4c5d6e7f8
Create Date: 2026-10-04 03:30:00.000000

"""
from alembic import op
import sqlalchemy as sa

revision = "b4c5d6e7f8a9"
down_revision = "a3b4c5d6e7f8"
branch_labels = None
depends_on = None


def upgrade():
    # ck_untimed_battery (BETWEEN 0 AND 100) already accepts NULL.
    op.alter_column("untimed_telemetry", "battery_level", existing_type=sa.Integer(), nullable=True)


def downgrade():
    # Refuse rather than invent a battery value for archived windows.
    count = op.get_bind().exec_driver_sql(
        "SELECT count(*) FROM untimed_telemetry WHERE battery_level IS NULL"
    ).scalar()
    if count:
        raise RuntimeError(f"{count} untimed rows have an unknown battery; downgrade would need a made-up value")
    op.alter_column("untimed_telemetry", "battery_level", existing_type=sa.Integer(), nullable=False)
