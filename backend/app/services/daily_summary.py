"""
Daily Behavior Aggregation Service (DailyBehaviorSummary)
=========================================================
Aggregates high-frequency ML behavior predictions into daily summaries
per animal per target-timezone day.
"""

import logging
from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple, List
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.daily_summary import DailyBehaviorSummary
from app.core.timezone import TARGET_TZ

logger = logging.getLogger(__name__)

def get_target_date_bounds(target_date: date) -> Tuple[datetime, datetime]:
    """
    Get start (00:00:00) and end (23:59:59.999999) timezone-aware datetimes
    for a given date in the configured target timezone.
    """
    start_local = datetime.combine(target_date, time.min, tzinfo=TARGET_TZ)
    end_local = datetime.combine(target_date, time.max, tzinfo=TARGET_TZ)
    return start_local, end_local


def aggregate_daily_behavior(
    db: Session,
    animal_id: int,
    target_date: date,
) -> Optional[DailyBehaviorSummary]:
    """
    Aggregate telemetry predictions for an animal on a target-timezone date.
    Filters strictly on `predicted_behavior IS NOT NULL`.

    Returns
    -------
    Optional[DailyBehaviorSummary]
        The created/updated summary instance, or None if n_predictions == 0.
    """
    start_dt, end_dt = get_target_date_bounds(target_date)

    # Filter telemetry for this animal and date window with valid ML predictions
    records = (
        db.query(Telemetry)
        .filter(
            Telemetry.animal_id == animal_id,
            Telemetry.time >= start_dt,
            Telemetry.time <= end_dt,
            Telemetry.predicted_behavior.in_(("Active", "Resting")),
        )
        .all()
    )

    n_predictions = len(records)
    if n_predictions == 0:
        logger.debug(f"Animal #{animal_id} on {target_date}: 0 predictions found. Skipping summary.")
        return None

    # Calculate behavior counts and percentage
    n_active = sum(1 for r in records if r.predicted_behavior == "Active")
    n_resting = sum(1 for r in records if r.predicted_behavior == "Resting")

    pct_active = (n_active / n_predictions) * 100.0
    pct_resting = (n_resting / n_predictions) * 100.0

    # Calculate average confidence
    confidences = [r.behavior_confidence for r in records if r.behavior_confidence is not None]
    avg_confidence = (sum(confidences) / len(confidences)) if confidences else None

    # Upsert logic (Insert or Update if (animal_id, date) already exists)
    summary = (
        db.query(DailyBehaviorSummary)
        .filter(
            DailyBehaviorSummary.animal_id == animal_id,
            DailyBehaviorSummary.date == target_date,
        )
        .first()
    )

    if summary:
        summary.pct_active = pct_active
        summary.pct_resting = pct_resting
        summary.n_predictions = n_predictions
        summary.avg_confidence = avg_confidence
        logger.info(f"Updated DailyBehaviorSummary for Animal #{animal_id} on {target_date}")
    else:
        summary = DailyBehaviorSummary(
            animal_id=animal_id,
            date=target_date,
            pct_active=pct_active,
            pct_resting=pct_resting,
            n_predictions=n_predictions,
            avg_confidence=avg_confidence,
            created_at=datetime.utcnow(),
        )
        db.add(summary)
        logger.info(f"Created DailyBehaviorSummary for Animal #{animal_id} on {target_date}")

    db.commit()
    db.refresh(summary)
    return summary


def aggregate_all_daily_behaviors(
    db: Session,
    target_date: Optional[date] = None,
) -> List[DailyBehaviorSummary]:
    """
    Run daily aggregation for all animals.
    If target_date is None, defaults to yesterday in the target timezone.
    """
    if target_date is None:
        yesterday = (datetime.now(TARGET_TZ) - timedelta(days=1)).date()
        target_date = yesterday

    animals = db.query(Animal).all()
    summaries = []

    for animal in animals:
        res = aggregate_daily_behavior(db, animal.id, target_date)
        if res:
            summaries.append(res)

    logger.info(f"Aggregated daily behavior for {len(summaries)}/{len(animals)} animals for date {target_date}")
    return summaries
