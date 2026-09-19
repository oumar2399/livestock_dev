"""Add persistent revocation, loss history and telemetry provenance (no backfill)."""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "4e0a2c3d5b7f"
down_revision = "3d9f1b2c4a6e"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("devices", sa.Column("ingestion_revoked_at", sa.DateTime(timezone=True)))
    for name, kind in (
        ("received_at", sa.DateTime(timezone=True)), ("time_source", sa.String(24)),
        ("protocol_version", sa.Integer()), ("behavior_eligible", sa.Boolean()),
        ("exclusion_reason", sa.String(50)),
    ):
        op.add_column("telemetry", sa.Column(name, kind))
    op.create_table("device_loss_periods",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("device_id", sa.String(50), sa.ForeignKey("devices.id"), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True)),
        sa.Column("declared_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("declared_by", sa.Integer(), sa.ForeignKey("users.id", ondelete="SET NULL")),
        sa.Column("audit", postgresql.JSONB(), nullable=False),
        sa.CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="ck_loss_period_bounds"),
    )
    op.create_index("idx_loss_device_start", "device_loss_periods", ["device_id", "started_at"])
    op.create_index("uq_loss_open_device", "device_loss_periods", ["device_id"], unique=True,
                    postgresql_where=sa.text("ended_at IS NULL"))
    op.create_table("behavior_rebuilds",
        sa.Column("animal_id", sa.Integer(), sa.ForeignKey("animals.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("date", sa.Date(), primary_key=True),
    )


def downgrade():
    op.drop_table("behavior_rebuilds")
    op.drop_table("device_loss_periods")
    for name in ("exclusion_reason", "behavior_eligible", "protocol_version", "time_source", "received_at"):
        op.drop_column("telemetry", name)
    op.drop_column("devices", "ingestion_revoked_at")
