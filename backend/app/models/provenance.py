"""
Modèle AnimalTrackingPeriod - Registre prospectif de provenance et de suivi historique.
Garantit l'absence de fuite de données lors de transferts d'animaux ou de réassignations de colliers.
"""
from datetime import datetime
from sqlalchemy import Column, BigInteger, Integer, String, DateTime, ForeignKey, Index, text
from sqlalchemy.orm import relationship
from app.db.database import Base


class AnimalTrackingPeriod(Base):
    __tablename__ = "animal_tracking_periods"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    animal_id = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False)
    device_id = Column(String(50), ForeignKey("devices.id", ondelete="SET NULL"), nullable=True)
    farm_id = Column(Integer, ForeignKey("farms.id", ondelete="CASCADE"), nullable=False)
    valid_from = Column(DateTime(timezone=True), nullable=False)
    valid_to = Column(DateTime(timezone=True), nullable=True)
    recorded_at = Column(DateTime(timezone=True), default=datetime.utcnow, nullable=False)
    source = Column(String(50), nullable=False)

    # Relations
    animal = relationship("Animal")
    device = relationship("Device")
    farm = relationship("Farm")

    __table_args__ = (
        Index("uq_tracking_open_animal", "animal_id", unique=True,
              postgresql_where=text("valid_to IS NULL")),
        Index("idx_tracking_periods_farm", "farm_id", "valid_from", "valid_to"),
        Index("idx_tracking_periods_animal", "animal_id", "valid_from", "valid_to"),
        Index("idx_tracking_periods_device", "device_id"),
    )
