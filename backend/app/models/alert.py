"""
Modèle Alert - Alertes santé/sécurité
"""
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base

class Alert(Base):
    """
    Table alerts - Alertes générées par système
    """
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False)
    type = Column(String(50), nullable=False)  # health, geofence, battery, offline
    severity = Column(String(20), nullable=False)  # info, warning, critical
    title = Column(String(255))
    message = Column(Text)
    triggered_at = Column(DateTime, default=datetime.utcnow, index=True)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(Integer, ForeignKey("users.id"))
    resolved_at = Column(DateTime, index=True)
    alert_metadata = Column(JSONB)  # Données spécifiques JSON
    
    # Relations
    animal = relationship("Animal", back_populates="alerts")