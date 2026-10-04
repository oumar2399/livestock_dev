"""Run the daily pipeline while preserving an independent audit record."""

import zlib
from datetime import date, timedelta
from typing import Literal, Optional

from sqlalchemy import text

from app.core.config import TARGET_TIMEZONE
from app.core.timezone import utc_now
from app.db.database import SessionLocal, engine
from app.models.job_run import DailyJobRun
from app.services.daily_pipeline import get_yesterday_target, run_daily_pipeline


DAILY_PIPELINE_JOB_NAME = "daily_behavior_pipeline"
# A run still "running" after this long is considered dead (process killed, crash).
STALE_RUN_AFTER = timedelta(hours=2)


class JobAlreadyRunning(RuntimeError):
    """Another run of the same job and target date holds the lock."""


def _lock_keys(job_name: str, target_date: date) -> tuple[int, int]:
    # Two signed int4 keys: one per job name, one per target date.
    return zlib.crc32(job_name.encode("utf-8")) & 0x7FFFFFFF, target_date.toordinal()


def mark_stale_runs(db, job_name: str, now=None) -> int:
    now = now or utc_now()
    stale = db.query(DailyJobRun).filter(
        DailyJobRun.job_name == job_name,
        DailyJobRun.status == "running",
        DailyJobRun.started_at < now - STALE_RUN_AFTER,
    ).all()
    for run in stale:
        run.status = "failed"
        run.finished_at = now
        run.error_message = f"stale: no completion within {STALE_RUN_AFTER}"
    return len(stale)


def run_daily_pipeline_tracked(
    target_date: Optional[date] = None,
    trigger_source: Literal["scheduled", "manual"] = "scheduled",
    initiated_by: Optional[int] = None,
) -> dict:
    effective_date = target_date or get_yesterday_target()

    # Transaction-scoped advisory lock on a dedicated connection: it is released
    # when that transaction ends, so a pooled connection never keeps it.
    lock_connection = engine.connect()
    lock_transaction = lock_connection.begin()
    try:
        acquired = lock_connection.execute(
            text("SELECT pg_try_advisory_xact_lock(:k1, :k2)"),
            dict(zip(("k1", "k2"), _lock_keys(DAILY_PIPELINE_JOB_NAME, effective_date))),
        ).scalar()
        if not acquired:
            raise JobAlreadyRunning(
                f"{DAILY_PIPELINE_JOB_NAME} is already running for {effective_date.isoformat()}"
            )
        return _run_locked(effective_date, trigger_source, initiated_by)
    finally:
        lock_transaction.rollback()
        lock_connection.close()


def _run_locked(effective_date, trigger_source, initiated_by) -> dict:
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
        mark_stale_runs(tracking_db, DAILY_PIPELINE_JOB_NAME)
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
