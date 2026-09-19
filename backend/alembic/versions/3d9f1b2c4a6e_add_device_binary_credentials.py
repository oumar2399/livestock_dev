"""Add optional device binary identifiers and secret fingerprints."""

from alembic import op
import sqlalchemy as sa


revision = "3d9f1b2c4a6e"
down_revision = "2c8e0f6a7b9d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("devices", sa.Column("transport_id", sa.Integer(), nullable=True))
    op.add_column("devices", sa.Column("device_secret", sa.String(64), nullable=True))
    op.create_unique_constraint("uq_devices_transport_id", "devices", ["transport_id"])
    op.create_check_constraint("ck_devices_transport_id_range", "devices", "transport_id IS NULL OR transport_id BETWEEN 1 AND 65535")
    op.create_check_constraint(
        "ck_devices_binary_credentials_pair", "devices",
        "(transport_id IS NULL AND device_secret IS NULL) OR "
        "(transport_id IS NOT NULL AND device_secret IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ck_devices_binary_credentials_pair", "devices", type_="check")
    op.drop_constraint("ck_devices_transport_id_range", "devices", type_="check")
    op.drop_constraint("uq_devices_transport_id", "devices", type_="unique")
    op.drop_column("devices", "device_secret")
    op.drop_column("devices", "transport_id")
