"""
Admin API Router — System Maintenance & Manual Batch Jobs
=========================================================
Endpoints requiring admin privileges for manually triggering pipelines,
re-evaluations, and background job maintenance.
"""

import logging
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.db.database import get_db
from app.models.user import User
from app.core.dependencies import require_admin
from app.schemas.health import SystemStatusResponse
from app.services.system_health import build_system_status
from app.models.job_run import DailyJobRun
from app.schemas.job_run import DailyJobRunList, DailyJobRunResponse
from app.services.job_tracking import run_daily_pipeline_tracked

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


@router.get(
    "/system-status",
    response_model=SystemStatusResponse,
    summary="Inspect database, model, schema and scheduler health",
)
def get_system_status(
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    return build_system_status(db)


@router.post(
    "/run-daily-jobs",
    status_code=status.HTTP_200_OK,
    summary="Trigger daily behavior pipeline manually",
    description=(
        "Manually triggers the daily behavior aggregation and anomaly evaluation "
        "pipeline for a specific target_date (or target-timezone yesterday by default). "
        "Requires Admin role."
    ),
)
def trigger_daily_pipeline(
    target_date: Optional[date] = Query(
        None,
        description="Target date (YYYY-MM-DD). Defaults to target-timezone yesterday."
    ),
    current_user: User = Depends(require_admin),
):
    """
    Manual pipeline trigger endpoint.
    Protected by JWT authentication (Admin role required).
    """
    logger.info(f"👨‍💼 Admin #{current_user.id} ({current_user.email}) triggered daily pipeline for {target_date or 'yesterday'}")
    return run_daily_pipeline_tracked(
        target_date=target_date,
        trigger_source="manual",
        initiated_by=current_user.id,
    )


@router.get("/daily-job-runs", response_model=DailyJobRunList)
def list_daily_job_runs(
    run_status: Optional[str] = Query(None, alias="status", pattern="^(running|success|failed)$"),
    target_date: Optional[date] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    query = db.query(DailyJobRun)
    if run_status:
        query = query.filter(DailyJobRun.status == run_status)
    if target_date:
        query = query.filter(DailyJobRun.target_date == target_date)
    total = query.count()
    runs = query.order_by(DailyJobRun.started_at.desc()).offset(offset).limit(limit).all()
    return {"total": total, "runs": runs, "limit": limit, "offset": offset}


@router.get("/daily-job-runs/{run_id}", response_model=DailyJobRunResponse)
def get_daily_job_run(
    run_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    run = db.query(DailyJobRun).filter(DailyJobRun.id == run_id).first()
    if not run:
        raise HTTPException(status_code=404, detail="Job execution not found")
    return run
