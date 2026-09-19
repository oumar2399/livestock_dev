"""Loss intervals and durable requests to rebuild derived behavior summaries."""

from sqlalchemy import Column, Integer, String, DateTime, Date, ForeignKey, CheckConstraint, Index, text
from sqlalchemy.dialects.postgresql import JSONB
from app.db.database import Base


class DeviceLossPeriod(Base):
    __tablename__ = "device_loss_periods"
    id = Column(Integer, primary_key=True)
    device_id = Column(String(50), ForeignKey("devices.id"), nullable=False)
    started_at = Column(DateTime(timezone=True), nullable=False)
    ended_at = Column(DateTime(timezone=True))
    declared_at = Column(DateTime(timezone=True), nullable=False)
    declared_by = Column(Integer, ForeignKey("users.id", ondelete="SET NULL"))
    audit = Column(JSONB, nullable=False)
    __table_args__ = (
        CheckConstraint("ended_at IS NULL OR ended_at > started_at", name="ck_loss_period_bounds"),
        Index("idx_loss_device_start", "device_id", "started_at"),
        Index("uq_loss_open_device", "device_id", unique=True,
              postgresql_where=text("ended_at IS NULL")),
    )


class BehaviorRebuild(Base):
    __tablename__ = "behavior_rebuilds"
    animal_id = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), primary_key=True)
    date = Column(Date, primary_key=True)
