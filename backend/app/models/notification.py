"""
Modèles pour les notifications ciblées :
- PushDevice : terminaux mobiles et tokens push
- NotificationPreference : préférences utilisateur (catégories, sévérité minimale)
- NotificationDelivery : outbox transactionnelle garantissant l'idempotence et la traçabilité
"""
from datetime import datetime
from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    ForeignKey,
    Text,
    Index,
    UniqueConstraint,
    CheckConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship

from app.db.database import Base


class PushDevice(Base):
    """
    Table push_devices — Enregistrement des terminaux et tokens push par utilisateur.
    """
    __tablename__ = "push_devices"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    provider = Column(String(50), default="expo", nullable=False)
    # Layout mirrors migration 8c4e6a1b2d3f: named unique constraint + plain index.
    push_token = Column(String(255), nullable=False, index=True)
    platform = Column(String(50), nullable=True)  # "ios", "android", "web"
    active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )
    last_seen_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    user = relationship("User", backref="push_devices")

    __table_args__ = (
        UniqueConstraint("push_token", name="uq_push_devices_token"),
    )


class NotificationPreference(Base):
    """
    Table notification_preferences — Préférences de notification par utilisateur et ferme optionnelle.
    """
    __tablename__ = "notification_preferences"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farm_id = Column(
        Integer,
        ForeignKey("farms.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    categories = Column(JSONB, nullable=False, default=list)  # ex: ["geofence", "health", "battery", "offline"]
    min_severity = Column(String(20), nullable=False, default="info")  # "info", "warning", "critical"
    enabled = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at = Column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    user = relationship("User", backref="notification_preferences")
    farm = relationship("Farm")

    __table_args__ = (
        CheckConstraint(
            "min_severity IN ('info', 'warning', 'critical')",
            name="ck_notification_pref_severity",
        ),
    )


class NotificationDelivery(Base):
    """
    Table notification_deliveries — Outbox durable pour le dispatching des alertes.
    Garantit l'idempotence (UNIQUE alert_id, user_id, channel, event_type).
    """
    __tablename__ = "notification_deliveries"

    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(
        Integer,
        ForeignKey("alerts.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    farm_id = Column(
        Integer,
        ForeignKey("farms.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    user_id = Column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    device_id = Column(
        Integer,
        ForeignKey("push_devices.id", ondelete="SET NULL"),
        nullable=True,
    )
    channel = Column(String(20), default="push", nullable=False)
    event_type = Column(String(50), default="alert_created", nullable=False)
    status = Column(String(20), default="pending", nullable=False)  # pending, sending, sent, retry, failed, cancelled
    attempt_count = Column(Integer, default=0, nullable=False)
    # Naive UTC from the ORM; server_default mirrors migration 8c4e6a1b2d3f.
    # Indexed only through the composite idx_notification_deliveries_poll.
    next_attempt_at = Column(DateTime, default=datetime.utcnow, server_default=func.now(), nullable=False)
    last_error_code = Column(String(100), nullable=True)
    last_error_message = Column(Text, nullable=True)
    provider_message_id = Column(String(255), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    sent_at = Column(DateTime, nullable=True)

    alert = relationship("Alert")
    farm = relationship("Farm")
    user = relationship("User")
    device = relationship("PushDevice")

    __table_args__ = (
        UniqueConstraint(
            "alert_id",
            "user_id",
            "channel",
            "event_type",
            name="uq_notification_delivery_alert_user_channel",
        ),
        CheckConstraint(
            "status IN ('pending', 'sending', 'sent', 'retry', 'failed', 'cancelled')",
            name="ck_notification_delivery_status",
        ),
        Index("idx_notification_deliveries_poll", "status", "next_attempt_at"),
    )
