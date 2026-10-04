"""
Anomaly Detection Service — Behavioral Anomaly Detection & Safeguards
======================================================================
1. Warm-up Safeguard: at least MIN_HISTORY_DAYS distinct days of eligible telemetry
   in the MAX_WINDOW_DAYS days before the evaluated date.
2. Modified Z-Score (Iglewicz & Hoaglin, 1993) on DailyBehaviorSummary.pct_active:
   Z = 0.6745 * (x - median) / MAD. When MAD == 0 (more than half of the baseline
   days identical), the mean absolute deviation about the median is used instead:
   Z = (x - median) / (1.2533 * MeanAD). When both are 0 there is no Z-score.
3. Alert rule: |x - median| >= MIN_ACTIVITY_CHANGE_PTS percentage points AND
   |Z| >= Z_THRESHOLD (3.5, the value recommended by Iglewicz & Hoaglin). Without a
   Z-score, the change alone decides (warning, reason "baseline_without_variation").
4. Directional Alerts: 'activity_deviation_low' or 'activity_deviation_high',
   without making biological/diagnostic assumptions.
"""

import os
import logging
import statistics
from datetime import datetime, date, time, timedelta
from typing import Optional, Tuple, List
from sqlalchemy import func, cast, Date
from sqlalchemy.orm import Session

from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.daily_summary import DailyBehaviorSummary
from app.models.alert import Alert
from app.schemas.alert import AlertType, AlertSeverity
from app.core.timezone import TARGET_TZ
from app.core.config import TARGET_TIMEZONE
from app.services.telemetry_quality import eligible_clause, lock_behavior
from app.models.telemetry_quality import BehaviorRebuild
from app.services.behavior_coverage import insufficient_coverage_days

logger = logging.getLogger(__name__)

# Default configuration via environment variables
MIN_HISTORY_DAYS = int(os.getenv("MIN_HISTORY_DAYS", 10))
MAX_WINDOW_DAYS = int(os.getenv("MAX_WINDOW_DAYS", 20))
Z_THRESHOLD = float(os.getenv("Z_THRESHOLD", 3.5))
# No alert below this absolute change of pct_active (percentage points), whatever the Z-score.
MIN_ACTIVITY_CHANGE_PTS = float(os.getenv("MIN_ACTIVITY_CHANGE_PTS", 5))
# Heuristic tier, not from the literature: |Z| >= 4.5 is reported as "critical".
CRITICAL_Z_THRESHOLD = 4.5

MAD_CONSISTENCY = 0.6745      # Iglewicz & Hoaglin (1993)
MEAN_AD_CONSISTENCY = 1.2533  # sqrt(pi / 2): MeanAD scale for a normal distribution


def has_sufficient_history(
    db: Session,
    animal_id: int,
    min_days: int = MIN_HISTORY_DAYS,
    max_window_days: int = MAX_WINDOW_DAYS,
    target_date: Optional[date] = None,
) -> bool:
    """
    Check if an animal has eligible telemetry on at least `min_days` distinct local
    days (TARGET_TIMEZONE) within the `max_window_days` days BEFORE `target_date`
    (the evaluated date, excluded). Defaults to today's local date.
    """
    target_date = target_date or datetime.now(TARGET_TZ).date()
    window_start = datetime.combine(target_date - timedelta(days=max_window_days), time.min, tzinfo=TARGET_TZ)
    window_end = datetime.combine(target_date, time.min, tzinfo=TARGET_TZ)

    distinct_days_count = (
        db.query(func.count(func.distinct(cast(func.timezone(TARGET_TIMEZONE, Telemetry.time), Date))))
        .filter(
            Telemetry.animal_id == animal_id,
            Telemetry.time >= window_start,
            Telemetry.time < window_end,
            eligible_clause(),
        )
        .scalar()
    ) or 0

    has_enough = distinct_days_count >= min_days
    logger.debug(
        f"Animal #{animal_id} warm-up check: {distinct_days_count}/{min_days} distinct days "
        f"in the {max_window_days} days before {target_date}. Sufficient = {has_enough}"
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
    |Modified Z-score| per Iglewicz & Hoaglin (1993): |0.6745 * (val - median) / MAD|.
    MAD must be > 0; use score_deviation() for the MAD == 0 fallbacks.
    """
    if mad_val <= 0:
        raise ValueError("MAD must be positive; use score_deviation() when MAD == 0")
    return abs(MAD_CONSISTENCY * (val - median_val) / mad_val)


def score_deviation(value: float, baseline: List[float]) -> Tuple[Optional[float], str, float, float, float]:
    """
    Robust deviation of `value` from `baseline`.

    Returns (|Z| or None, scale, median, MAD, MeanAD) where scale is:
      "MAD"    : Z = 0.6745 * (x - median) / MAD
      "MeanAD" : MAD == 0, Z = (x - median) / (1.2533 * MeanAD), MeanAD about the median
      "none"   : MAD == MeanAD == 0 (all baseline days identical), no Z-score
    """
    median_val, mad_val = compute_median_and_mad(baseline)
    mean_ad = statistics.fmean(abs(v - median_val) for v in baseline) if baseline else 0.0
    if mad_val > 0:
        return compute_modified_z_score(value, median_val, mad_val), "MAD", median_val, mad_val, mean_ad
    if mean_ad > 0:
        return abs(value - median_val) / (MEAN_AD_CONSISTENCY * mean_ad), "MeanAD", median_val, mad_val, mean_ad
    return None, "none", median_val, mad_val, mean_ad


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
    lock_behavior(db, animal_id)
    if db.query(BehaviorRebuild).filter_by(animal_id=animal_id).first():
        return None
    if db.query(Alert.id).filter(
        Alert.animal_id == animal_id,
        Alert.alert_metadata["target_date"].astext == target_date.isoformat(),
        Alert.alert_metadata["quality_invalidated_at"].astext.is_not(None),
    ).first():
        return None
    # 1. Warm-up safeguard (history before the evaluated date)
    if not has_sufficient_history(db, animal_id, min_days=min_days, max_window_days=max_window_days,
                                  target_date=target_date):
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

    excluded_days = insufficient_coverage_days(db, animal_id, target_date - timedelta(days=max_window_days), target_date)
    if target_date in excluded_days:
        logger.info("Insufficient or unconfigured window coverage for animal %s", animal_id)
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

    baseline_pcts = [s.pct_active for s in baseline_summaries if s.date not in excluded_days]
    if len(baseline_pcts) < min_days:
        logger.info(f"Animal #{animal_id}: Baseline count ({len(baseline_pcts)}) < {min_days} on {target_date}. Skipping.")
        return None

    # 4. Robust deviation (MAD, MeanAD fallback, or no Z-score)
    z_score, z_scale, median_val, mad_val, mean_ad = score_deviation(target_summary.pct_active, baseline_pcts)
    change_pts = abs(target_summary.pct_active - median_val)
    z_text = "n/a" if z_score is None else f"{z_score:.2f}"

    logger.info(
        f"Animal #{animal_id} on {target_date}: pct_active={target_summary.pct_active:.1f}%, "
        f"baseline_median={median_val:.1f}%, MAD={mad_val:.2f}, MeanAD={mean_ad:.2f}, "
        f"scale={z_scale}, Z={z_text}"
    )

    # 5. Alert rule: a minimum absolute change, then the Z threshold when a Z exists.
    if change_pts < MIN_ACTIVITY_CHANGE_PTS:
        return None
    if z_score is not None and z_score < z_threshold:
        return None

    # Retrieve animal for notification text
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    animal_name = animal.name if animal else f"Animal #{animal_id}"

    # Symmetric severity; without a Z-score the alert is a warning.
    severity = (AlertSeverity.CRITICAL.value
                if z_score is not None and z_score >= CRITICAL_Z_THRESHOLD
                else AlertSeverity.WARNING.value)

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

    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    farm_id = animal.farm_id if animal else None

    # Create and save new Alert
    alert = Alert(
        animal_id=animal_id,
        farm_id=farm_id,
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
            "baseline_mean_ad": round(mean_ad, 4),
            "z_scale": z_scale,
            "z_score": None if z_score is None else round(z_score, 2),
            **({"reason": "baseline_without_variation"} if z_scale == "none" else {}),
            "delta_pct": round(delta_pct, 1),
            "unit": unit,
        },
    )

    db.add(alert)
    db.flush()
    # Intent in the alert's transaction; a failure only rolls back its savepoint.
    from app.services.notification_service import enqueue_in_savepoint
    enqueue_in_savepoint(db, [alert])
    db.commit()
    db.refresh(alert)

    logger.warning(
        f"ANOMALY ALERT CREATED: [{severity.upper()}] {title} - {message} (scale={z_scale}, Z={z_text})"
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

    animals = db.query(Animal).order_by(Animal.id).all()
    created_alerts = []

    for animal in animals:
        alert = evaluate_animal_anomaly(db, animal.id, target_date, z_threshold=z_threshold)
        if alert:
            created_alerts.append(alert)

    logger.info(f"Evaluated anomalies for {len(animals)} animals on {target_date}. Generated {len(created_alerts)} alerts.")
    return created_alerts
