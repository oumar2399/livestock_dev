"""
Device model - M5Stack sensors
Maps to the 'devices' table defined in schema.sql
"""
from sqlalchemy import Column, String, Integer, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base


class Device(Base):
    __tablename__ = "devices"

    id               = Column(String(50), primary_key=True)   # ex: "M5-001"
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