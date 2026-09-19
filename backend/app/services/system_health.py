"""Fast, side-effect-free application health checks."""

from time import perf_counter
from typing import Any

from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.config import TARGET_TIMEZONE, settings
from app.core.timezone import utc_now
from app.services.ml_inference import get_model_info, get_profile_status


def _database_health(db: Session) -> dict[str, Any]:
    started = perf_counter()
    try:
        db.execute(text("SELECT 1"))
    except Exception:
        db.rollback()
        return {"status": "down", "latency_ms": None}
    return {
        "status": "up",
        "latency_ms": round((perf_counter() - started) * 1000, 2),
    }


def _schema_health(db: Session, database_is_up: bool) -> dict[str, Any]:
    if not database_is_up:
        return {"revision": None}
    try:
        revision = db.execute(
            text("SELECT version_num FROM alembic_version")
        ).scalar_one_or_none()
    except Exception:
        db.rollback()
        revision = None
    return {"revision": revision}


def _model_health() -> dict[str, Any]:
    info = get_model_info()
    if info is None:
        return {"status": "unavailable", "classes": [], "profiles": get_profile_status()}
    return {"status": "loaded", "classes": info.get("classes", []), "profiles": get_profile_status()}


def _scheduler_health() -> dict[str, Any]:
    from app.core.scheduler import scheduler

    job = scheduler.get_job("daily_behavior_pipeline")
    return {
        "enabled": settings.SCHEDULER_ENABLED,
        "running": scheduler.running,
        "next_run_at": job.next_run_time if job else None,
    }


def build_readiness(db: Session) -> dict[str, Any]:
    database = _database_health(db)
    model = _model_health()
    ready = database["status"] == "up" and model["status"] == "loaded"
    return {
        "status": "ready" if ready else "not_ready",
        "checked_at": utc_now(),
    }


def build_system_status(db: Session) -> dict[str, Any]:
    database = _database_health(db)
    model = _model_health()
    scheduler = _scheduler_health()
    database_is_up = database["status"] == "up"

    if not database_is_up:
        status = "unhealthy"
    elif model["status"] != "loaded":
        status = "degraded"
    elif scheduler["enabled"] and not scheduler["running"]:
        status = "degraded"
    else:
        status = "healthy"

    return {
        "status": status,
        "checked_at": utc_now(),
        "target_timezone": TARGET_TIMEZONE,
        "database": database,
        "model": model,
        "schema": _schema_health(db, database_is_up),
        "scheduler": scheduler,
    }
