"""Add notifications tables: push_devices, notification_preferences, notification_deliveries

Revision ID: 8c4e6a1b2d3f
Revises: 7b3d5f6a8c9e
Create Date: 2026-09-22 22:40:00.000000

"""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "8c4e6a1b2d3f"
down_revision = "7b3d5f6a8c9e"
branch_labels = None
depends_on = None


def upgrade():
    # 1. Table push_devices
    op.create_table(
        "push_devices",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("provider", sa.String(length=50), server_default="expo", nullable=False),
        sa.Column("push_token", sa.String(length=255), nullable=False),
        sa.Column("platform", sa.String(length=50), nullable=True),
        sa.Column("active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_seen_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("push_token", name="uq_push_devices_token"),
    )
    op.create_index("ix_push_devices_user_id", "push_devices", ["user_id"])
    op.create_index("ix_push_devices_push_token", "push_devices", ["push_token"])

    # 2. Table notification_preferences
    op.create_table(
        "notification_preferences",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=True),
        sa.Column("categories", postgresql.JSONB(astext_type=sa.Text()), server_default="[]", nullable=False),
        sa.Column("min_severity", sa.String(length=20), server_default="info", nullable=False),
        sa.Column("enabled", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.CheckConstraint("min_severity IN ('info', 'warning', 'critical')", name="ck_notification_pref_severity"),
    )
    op.create_index("ix_notification_preferences_user_id", "notification_preferences", ["user_id"])
    op.create_index("ix_notification_preferences_farm_id", "notification_preferences", ["farm_id"])

    # 3. Table notification_deliveries (Outbox)
    op.create_table(
        "notification_deliveries",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("alert_id", sa.Integer(), sa.ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False),
        sa.Column("farm_id", sa.Integer(), sa.ForeignKey("farms.id", ondelete="CASCADE"), nullable=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("device_id", sa.Integer(), sa.ForeignKey("push_devices.id", ondelete="SET NULL"), nullable=True),
        sa.Column("channel", sa.String(length=20), server_default="push", nullable=False),
        sa.Column("event_type", sa.String(length=50), server_default="alert_created", nullable=False),
        sa.Column("status", sa.String(length=20), server_default="pending", nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("last_error_code", sa.String(length=100), nullable=True),
        sa.Column("last_error_message", sa.Text(), nullable=True),
        sa.Column("provider_message_id", sa.String(length=255), nullable=True),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False),
        sa.Column("sent_at", sa.DateTime(), nullable=True),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("alert_id", "user_id", "channel", "event_type", name="uq_notification_delivery_alert_user_channel"),
        sa.CheckConstraint("status IN ('pending', 'sending', 'sent', 'retry', 'failed', 'cancelled')", name="ck_notification_delivery_status"),
    )
    op.create_index("ix_notification_deliveries_alert_id", "notification_deliveries", ["alert_id"])
    op.create_index("ix_notification_deliveries_farm_id", "notification_deliveries", ["farm_id"])
    op.create_index("ix_notification_deliveries_user_id", "notification_deliveries", ["user_id"])
    op.create_index("idx_notification_deliveries_poll", "notification_deliveries", ["status", "next_attempt_at"])


def downgrade():
    op.drop_table("notification_deliveries")
    op.drop_table("notification_preferences")
    op.drop_table("push_devices")
