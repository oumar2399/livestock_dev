"""
Modèles Feedback - Retours utilisateurs (bergers/vétérinaires)
- PredictionFeedback : validation/correction des prédictions comportementales ML (Active/Resting)
- AlertFeedback      : confirmation/infirmation des alertes de déviation comportementale
"""
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Text, UniqueConstraint
from sqlalchemy.orm import relationship
from datetime import datetime
from app.db.database import Base


class PredictionFeedback(Base):
    """
    Feedback utilisateur sur une prédiction comportementale ML spécifique.
    """
    __tablename__ = "prediction_feedbacks"

    id                  = Column(Integer, primary_key=True, index=True, autoincrement=True)
    animal_id           = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id             = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    telemetry_time      = Column(DateTime, nullable=False, index=True)
    predicted_behavior  = Column(String, nullable=True)
    confidence          = Column(Float, nullable=True)
    verdict             = Column(String(20), nullable=False)  # 'correct' | 'incorrect'
    correction          = Column(String(50), nullable=True)   # Vrai comportement si connu ('Active' | 'Resting')
    created_at          = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relations
    animal = relationship("Animal")
    user   = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "animal_id", "telemetry_time", name="uq_user_prediction_feedback"),
    )


class AlertFeedback(Base):
    """
    Feedback utilisateur sur une alerte de déviation comportementale.
    """
    __tablename__ = "alert_feedbacks"

    id         = Column(Integer, primary_key=True, index=True, autoincrement=True)
    alert_id   = Column(Integer, ForeignKey("alerts.id", ondelete="CASCADE"), nullable=False, index=True)
    animal_id  = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id    = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)

    alert_type = Column(String(50), nullable=False)   # Copie de alert.type (ex: activity_deviation_low)
    z_score    = Column(Float, nullable=True)        # Copie de alert.alert_metadata['z_score']
    verdict    = Column(String(30), nullable=False)  # 'confirmed_issue' | 'false_alarm'
    notes      = Column(Text, nullable=True)         # Remarques ou observations terrain
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relations
    alert  = relationship("Alert")
    animal = relationship("Animal")
    user   = relationship("User")

    __table_args__ = (
        UniqueConstraint("user_id", "alert_id", name="uq_user_alert_feedback"),
    )
