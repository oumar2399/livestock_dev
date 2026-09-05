"""
APScheduler Configuration & Lifecycle Management
=================================================
Manages automated daily execution of the behavior pipeline using APScheduler.
"""

import logging
from apscheduler.schedulers.background import BackgroundScheduler

from app.core.config import settings, TARGET_TIMEZONE
from app.core.timezone import TARGET_TZ
from app.services.job_tracking import run_daily_pipeline_tracked

logger = logging.getLogger(__name__)

scheduler = BackgroundScheduler(timezone=TARGET_TZ)


def run_daily_pipeline_job():
    """
    Background job wrapper executed by APScheduler.
    Delegates session and audit lifecycle to the tracked job service.
    """
    logger.info("⏰ Scheduler trigger: Starting daily behavior pipeline job...")
    try:
        run_daily_pipeline_tracked(trigger_source="scheduled")
    except Exception as e:
        logger.error(f"❌ Scheduled daily pipeline job failed with error: {e}", exc_info=True)


def start_scheduler():
    """
    Start the APScheduler background scheduler if enabled in settings.
    """
    if not settings.SCHEDULER_ENABLED:
        logger.info("ℹ️ Scheduler disabled (SCHEDULER_ENABLED=false). Skipping automated cron jobs.")
        return

    scheduler.add_job(
        run_daily_pipeline_job,
        trigger="cron",
        hour=settings.SCHEDULER_HOUR,
        minute=settings.SCHEDULER_MINUTE,
        timezone=TARGET_TZ,
        id="daily_behavior_pipeline",
        replace_existing=True,
        max_instances=1,
        coalesce=True,
    )
    scheduler.start()
    logger.info(
        f"✅ Scheduler started — Daily behavior job scheduled at "
        f"{settings.SCHEDULER_HOUR:02d}:{settings.SCHEDULER_MINUTE:02d} daily "
        f"({TARGET_TIMEZONE})."
    )


def stop_scheduler():
    """
    Shutdown the APScheduler background scheduler cleanly.
    """
    if scheduler.running:
        scheduler.shutdown()
        logger.info("🛑 Scheduler stopped cleanly.")
