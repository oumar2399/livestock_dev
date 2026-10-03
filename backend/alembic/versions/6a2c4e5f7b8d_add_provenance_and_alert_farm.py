"""Add animal_tracking_periods and alerts.farm_id for historical provenance.

Revision ID: 6a2c4e5f7b8d
Revises: 5f1b3d4e6c8a
Create Date: 2026-09-22 11:30:00.000000
"""

from alembic import op
import sqlalchemy as sa

revision = "6a2c4e5f7b8d"
down_revision = "5f1b3d4e6c8a"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Create animal_tracking_periods table
    op.create_table(
        "animal_tracking_periods",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("animal_id", sa.Integer(), sa.ForeignKey("animals.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.String(50), sa.ForeignKey("devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_to", sa.DateTime(timezone=True), nullable=True),
        sa.Column("recorded_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("source", sa.String(50), nullable=False),
    )
    op.create_index(
        "idx_tracking_periods_farm",
        "animal_tracking_periods",
        ["farm_id", "valid_from", "valid_to"],
    )
    op.create_index(
        "idx_tracking_periods_animal",
        "animal_tracking_periods",
        ["animal_id", "valid_from", "valid_to"],
    )
    op.create_index(
        "idx_tracking_periods_device",
        "animal_tracking_periods",
        ["device_id"],
    )

    # 2. Add farm_id column to alerts table
    op.add_column("alerts", sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=True))
    op.create_index("idx_alerts_farm", "alerts", ["farm_id", sa.text("triggered_at DESC")])


def downgrade():
    op.drop_index("idx_alerts_farm", table_name="alerts")
    op.drop_column("alerts", "farm_id")

    op.drop_index("idx_tracking_periods_device", table_name="animal_tracking_periods")
    op.drop_index("idx_tracking_periods_animal", table_name="animal_tracking_periods")
    op.drop_index("idx_tracking_periods_farm", table_name="animal_tracking_periods")
    op.drop_table("animal_tracking_periods")
