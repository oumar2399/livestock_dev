"""
Anomaly Detection Service — Behavioral Anomaly Detection & Safeguards
======================================================================
1. Warm-up Safeguard: Ensures animal has sufficient distinct days before evaluation.
2. Modified Z-Score: Computes robust Median and MAD statistics on DailyBehaviorSummary.
3. Directional Alerts: Triggers 'activity_deviation_low' or 'activity_deviation_high'
   without making biological/diagnostic assumptions.
"""

import os
import logging
import statistics
from datetime import datetime, date, timedelta
from typing import Optional, Tuple, List
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.daily_summary import DailyBehaviorSummary
from app.models.alert import Alert
from app.schemas.alert import AlertType, AlertSeverity
from app.core.timezone import TARGET_TZ, utc_now

logger = logging.getLogger(__name__)

# Default configuration via environment variables
MIN_HISTORY_DAYS = int(os.getenv("MIN_HISTORY_DAYS", 10))
MAX_WINDOW_DAYS = int(os.getenv("MAX_WINDOW_DAYS", 20))
Z_THRESHOLD = float(os.getenv("Z_THRESHOLD", 3.0))


def has_sufficient_history(
    db: Session,
    animal_id: int,
    min_days: int = MIN_HISTORY_DAYS,
    max_window_days: int = MAX_WINDOW_DAYS,
) -> bool:
    """
    Check if an animal has data for at least `min_days` distinct calendar days
    within the last `max_window_days` sliding window.
    """
    cutoff_time = utc_now() - timedelta(days=max_window_days)

    distinct_days_count = (
        db.query(func.count(func.distinct(cast(Telemetry.time, Date))))
        .filter(
            Telemetry.animal_id == animal_id,
            Telemetry.time >= cutoff_time,
        )
        .scalar()
    ) or 0

    has_enough = distinct_days_count >= min_days
    logger.debug(
        f"Animal #{animal_id} warm-up check: {distinct_days_count}/{min_days} distinct days "
        f"in the last {max_window_days} days. Sufficient = {has_enough}"
    )

    return has_enough


def compute_median_and_mad(values: List[float]) -> Tuple[float, float]:
    """
    Compute sample median and Median Absolute Deviation (MAD).

    Returns
    -------
    Tuple[float, float]
        (median_val, mad_val)
    """
    if not values:
        return 0.0, 0.0

    med_val = float(statistics.median(values))
    deviations = [abs(v - med_val) for v in values]
    mad_val = float(statistics.median(deviations))

    return med_val, mad_val


def compute_modified_z_score(val: float, median_val: float, mad_val: float) -> float:
    """
    Compute Modified Z-score using Boris Iglewicz and David Hoaglin's formula:
    Z = |val - median| / (1.4826 * MAD + 1e-6)
    """
    denom = 1.4826 * mad_val + 1e-6
    return abs(val - median_val) / denom


def evaluate_animal_anomaly(
    db: Session,
    animal_id: int,
    target_date: date,
    z_threshold: float = Z_THRESHOLD,
    min_days: int = MIN_HISTORY_DAYS,
    max_window_days: int = MAX_WINDOW_DAYS,
) -> Optional[Alert]:
    """
    Evaluate if an animal's behavior on target_date deviates significantly from baseline.

    Rules:
    - Warm-up check: Requires has_sufficient_history().
    - Uses DailyBehaviorSummary for target_date and baseline window.
    - Symmetric severity: 'critical' if Z >= 4.5, else 'warning'.
    - Directional classification:
      - pct_active < median -> 'activity_deviation_low'
      - pct_active > median -> 'activity_deviation_high'
    - Dynamic unit formatting: '%' if median > 0, ' pts' if median == 0.
    """
    # 1. Warm-up safeguard
    if not has_sufficient_history(db, animal_id, min_days=min_days, max_window_days=max_window_days):
        logger.info(f"Animal #{animal_id}: Insufficient history for anomaly detection on {target_date}. Skipping.")
        return None

    # 2. Get target day summary
    target_summary = (
        db.query(DailyBehaviorSummary)
        .filter(
            DailyBehaviorSummary.animal_id == animal_id,
            DailyBehaviorSummary.date == target_date,
        )
        .first()
    )

    if not target_summary:
        logger.warning(f"Animal #{animal_id}: No DailyBehaviorSummary on {target_date}. Skipping anomaly evaluation.")
        return None

    # 3. Get baseline window summaries (excluding target_date)
    start_date = target_date - timedelta(days=max_window_days)
    baseline_summaries = (
        db.query(DailyBehaviorSummary)
        .filter(
            DailyBehaviorSummary.animal_id == animal_id,
            DailyBehaviorSummary.date >= start_date,
            DailyBehaviorSummary.date < target_date,
        )
        .all()
    )

    baseline_pcts = [s.pct_active for s in baseline_summaries]
    if len(baseline_pcts) < min_days:
        logger.info(f"Animal #{animal_id}: Baseline count ({len(baseline_pcts)}) < {min_days} on {target_date}. Skipping.")
        return None

    # 4. Compute Median, MAD, and Z-score
    median_val, mad_val = compute_median_and_mad(baseline_pcts)
    z_score = compute_modified_z_score(target_summary.pct_active, median_val, mad_val)

    logger.info(
        f"Animal #{animal_id} on {target_date}: pct_active={target_summary.pct_active:.1f}%, "
        f"baseline_median={median_val:.1f}%, MAD={mad_val:.1f}%, Z-score={z_score:.2f}"
    )

    # 5. Check anomaly threshold
    if z_score < z_threshold:
        return None

    # Retrieve animal for notification text
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    animal_name = animal.name if animal else f"Animal #{animal_id}"

    # Symmetric severity classification
    severity = AlertSeverity.CRITICAL.value if z_score >= 4.5 else AlertSeverity.WARNING.value

    # Dynamic unit calculation (% vs pts)
    if median_val > 0:
        delta_pct = ((target_summary.pct_active - median_val) / median_val) * 100.0
        unit = "%"
    else:
        delta_pct = target_summary.pct_active - median_val
        unit = " pts"

    # Directional classification
    if target_summary.pct_active < median_val:
        alert_type = AlertType.ACTIVITY_DEVIATION_LOW.value
        title = f"Activité inhabituellement basse ({animal_name})"
        message = f"Activité inhabituellement basse ({delta_pct:.1f}{unit} vs habitude)"
    else:
        alert_type = AlertType.ACTIVITY_DEVIATION_HIGH.value
        title = f"Activité inhabituellement élevée ({animal_name})"
        message = f"Activité inhabituellement élevée (+{delta_pct:.1f}{unit} vs habitude)"

    # Idempotency check: prevent duplicate alert for same animal, type, and target_date
    existing_alert = (
        db.query(Alert)
        .filter(
            Alert.animal_id == animal_id,
            Alert.type == alert_type,
            Alert.alert_metadata["target_date"].astext == target_date.isoformat(),
        )
        .first()
    )

    if existing_alert:
        logger.info(f"Existing alert #{existing_alert.id} found for Animal #{animal_id} on {target_date}. Skipping duplicate.")
        return existing_alert

    # Create and save new Alert
    alert = Alert(
        animal_id=animal_id,
        type=alert_type,
        severity=severity,
        title=title,
        message=message,
        triggered_at=datetime.utcnow(),
        alert_metadata={
            "target_date": target_date.isoformat(),
            "pct_active": target_summary.pct_active,
            "baseline_median": median_val,
            "baseline_mad": mad_val,
            "z_score": round(z_score, 2),
            "delta_pct": round(delta_pct, 1),
            "unit": unit,
        },
    )

    db.add(alert)
    db.commit()
    db.refresh(alert)

    logger.warning(
        f"ANOMALY ALERT CREATED: [{severity.upper()}] {title} - {message} (Z={z_score:.2f})"
    )
    return alert


def evaluate_all_anomalies(
    db: Session,
    target_date: Optional[date] = None,
    z_threshold: float = Z_THRESHOLD,
) -> List[Alert]:
    """
    Evaluate behavioral anomalies for all animals for a specific target_date.
    Defaults to yesterday in the configured target timezone.
    """
    if target_date is None:
        yesterday = (datetime.now(TARGET_TZ) - timedelta(days=1)).date()
        target_date = yesterday

    animals = db.query(Animal).all()
    created_alerts = []

    for animal in animals:
        alert = evaluate_animal_anomaly(db, animal.id, target_date, z_threshold=z_threshold)
        if alert:
            created_alerts.append(alert)

    logger.info(f"Evaluated anomalies for {len(animals)} animals on {target_date}. Generated {len(created_alerts)} alerts.")
    return created_alerts
