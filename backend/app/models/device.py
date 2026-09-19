"""
Device model - M5Stack sensors
Maps to the 'devices' table defined in schema.sql
"""
from sqlalchemy import CheckConstraint, Column, String, Integer, DateTime, ForeignKey, Text, Index, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base


class Device(Base):
    __tablename__ = "devices"

    id               = Column(String(50), primary_key=True)   # ex: "M5-001"
    transport_id     = Column(Integer, nullable=True)
    device_secret    = Column(String(64), nullable=True)  # SHA-256 fingerprint, never the raw secret
    ingestion_revoked_at = Column(DateTime(timezone=True), nullable=True)
    farm_id          = Column(Integer, ForeignKey("farms.id"))
    model            = Column(String(100))
    firmware_version = Column(String(50))
    last_seen        = Column(DateTime)
    battery_capacity = Column(Integer)                        # last known battery %
    status           = Column(String(50), default="active")   # active/maintenance/lost/retired
    notes            = Column(Text)
    created_at       = Column(DateTime, default=datetime.utcnow)

    # Relationship
    farm = relationship("Farm", backref="devices")

    __table_args__ = (
        UniqueConstraint("transport_id", name="uq_devices_transport_id"),
        CheckConstraint("transport_id IS NULL OR transport_id BETWEEN 1 AND 65535", name="ck_devices_transport_id_range"),
        CheckConstraint(
            "(transport_id IS NULL AND device_secret IS NULL) OR "
            "(transport_id IS NOT NULL AND device_secret IS NOT NULL)",
            name="ck_devices_binary_credentials_pair",
        ),
        Index("idx_devices_farm", "farm_id"),
        Index("idx_devices_status", "status"),
    )
