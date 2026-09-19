"""
Daily Behavior Pipeline Service
===============================
Centralized orchestration for running daily behavior aggregation and anomaly evaluation.
Guarantees sequential execution:
  1. aggregate_all_daily_behaviors (populates DailyBehaviorSummary for target_date)
  2. evaluate_all_anomalies (evaluates anomalies based on DailyBehaviorSummary)
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session

from app.services.daily_summary import aggregate_all_daily_behaviors
from app.services.anomaly_detection import evaluate_all_anomalies
from app.core.timezone import TARGET_TZ, utc_now
from app.services.telemetry_quality import process_behavior_rebuilds

logger = logging.getLogger(__name__)


def get_yesterday_target() -> date:
    """Return yesterday's date in the configured target timezone."""
    return (datetime.now(TARGET_TZ) - timedelta(days=1)).date()


def run_daily_pipeline(
    db: Session,
    target_date: Optional[date] = None,
) -> Dict[str, Any]:
    """
    Run the full daily pipeline for target_date (defaults to target-timezone yesterday).

    Returns
    -------
    Dict[str, Any]
        Pipeline execution metrics and status summary.
    """
    if target_date is None:
        target_date = get_yesterday_target()

    logger.info(f"🚀 Starting daily behavior pipeline for target date: {target_date}")

    process_behavior_rebuilds(db)
    # 1. Daily Aggregation (must run first)
    summaries = aggregate_all_daily_behaviors(db, target_date=target_date)

    # 2. Anomaly Evaluation
    alerts = evaluate_all_anomalies(db, target_date=target_date)

    result = {
        "target_date": target_date.isoformat(),
        "summaries_created": len(summaries),
        "alerts_created": len(alerts),
        "executed_at": utc_now().isoformat(),
    }

    logger.info(
        f"✅ Daily behavior pipeline completed for {target_date}: "
        f"{len(summaries)} summaries, {len(alerts)} alerts generated."
    )

    return result
