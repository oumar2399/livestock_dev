"""Run the daily pipeline while preserving an independent audit record."""

from datetime import date
from typing import Literal, Optional

from app.core.config import TARGET_TIMEZONE
from app.core.timezone import utc_now
from app.db.database import SessionLocal
from app.models.job_run import DailyJobRun
from app.services.daily_pipeline import get_yesterday_target, run_daily_pipeline


DAILY_PIPELINE_JOB_NAME = "daily_behavior_pipeline"


def run_daily_pipeline_tracked(
    target_date: Optional[date] = None,
    trigger_source: Literal["scheduled", "manual"] = "scheduled",
    initiated_by: Optional[int] = None,
) -> dict:
    effective_date = target_date or get_yesterday_target()
    tracking_db = SessionLocal()
    pipeline_db = SessionLocal()
    job_run = DailyJobRun(
        job_name=DAILY_PIPELINE_JOB_NAME,
        trigger_source=trigger_source,
        target_date=effective_date,
        timezone_name=TARGET_TIMEZONE,
        status="running",
        started_at=utc_now(),
        initiated_by=initiated_by,
    )

    try:
        tracking_db.add(job_run)
        tracking_db.commit()
        tracking_db.refresh(job_run)

        result = run_daily_pipeline(pipeline_db, target_date=effective_date)
        job_run.status = "success"
        job_run.summaries_created = result["summaries_created"]
        job_run.alerts_created = result["alerts_created"]
        job_run.finished_at = utc_now()
        tracking_db.commit()

        return {**result, "job_run_id": job_run.id}
    except Exception as exc:
        pipeline_db.rollback()
        if job_run.id is not None:
            job_run.status = "failed"
            job_run.finished_at = utc_now()
            job_run.error_message = str(exc)[:2000]
            try:
                tracking_db.commit()
            except Exception:
                tracking_db.rollback()
        raise
    finally:
        pipeline_db.close()
        tracking_db.close()
