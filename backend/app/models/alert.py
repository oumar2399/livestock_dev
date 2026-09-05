"""
Modèle Alert - Alertes santé/sécurité
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text, Index, desc, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class Alert(Base):
    """
    Table alerts - Alertes générées par système
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True)
    animal_id = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False)  # health, geofence, battery, offline
    severity = Column(String(20), nullable=False)  # info, warning, critical
    title = Column(String(255))
    message = Column(Text)
    triggered_at = Column(DateTime, default=datetime.utcnow)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    resolved_at = Column(DateTime)
    alert_metadata = Column(JSONB)  # Données spécifiques JSON
    
    # Relations
    animal = relationship("Animal", back_populates="alerts")

    __table_args__ = (
        Index("idx_alerts_animal", "animal_id", desc("triggered_at")),
        Index("idx_alerts_severity", "severity", desc("triggered_at")),
        Index(
            "idx_alerts_unresolved",
            "resolved_at",
            postgresql_where=text("resolved_at IS NULL"),
        ),
        Index("ix_alerts_animal_type", "animal_id", "type"),
        Index("ix_alerts_metadata_gin", "alert_metadata", postgresql_using="gin"),
        Index(
            "uq_alerts_animal_type_target_date",
            "animal_id",
            "type",
            text("(alert_metadata ->> 'target_date')"),
            unique=True,
            postgresql_where=text("alert_metadata ? 'target_date'"),
        ),
    )
