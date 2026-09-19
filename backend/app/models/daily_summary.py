"""
DailyBehaviorSummary Model — Daily Aggregated Behavioral Metrics
================================================================
Stores daily percentages of Active vs Resting behavior, count of predictions,
and average model confidence per animal per target-timezone day.
Used for long-term anomaly detection baselines and mobile time budget.
"""

from datetime import datetime
from sqlalchemy import Column, Integer, Float, Date, DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import backref, relationship

from app.db.database import Base


class DailyBehaviorSummary(Base):
    __tablename__ = "daily_behavior_summary"

    id = Column(Integer, primary_key=True, index=True)
    animal_id = Column(Integer, ForeignKey("animals.id", ondelete="CASCADE"), nullable=False, index=True)
    date = Column(Date, nullable=False, index=True)

    pct_active = Column(Float, nullable=False)
    pct_resting = Column(Float, nullable=False)
    n_predictions = Column(Integer, nullable=False)
    avg_confidence = Column(Float, nullable=True)

    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    animal = relationship(
        "Animal",
        backref=backref(
            "daily_behavior_summaries", cascade="all, delete-orphan", passive_deletes=True
        ),
    )

    __table_args__ = (
        UniqueConstraint("animal_id", "date", name="uq_animal_date"),
    )
