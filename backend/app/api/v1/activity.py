"""
Activity Summary API - Farm-scoped behavioral analysis endpoints

GET /activity/summary/{animal_id}   -> Daily activity budget (pie chart data)
GET /activity/weekly/{animal_id}    -> 7-day trend
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func, cast, Integer
from datetime import date, datetime, timedelta
from typing import Optional
from collections import Counter

from app.db.database import get_db
from app.models.telemetry import Telemetry
from app.models.animal import Animal
from app.models.user import User
from app.schemas.activity import (
    ActivitySummary, ActivityBudget, ActivityBudgetItem,
    ActivityAverages, HourlyBreakdown
)
from app.core.dependencies import get_current_user
from app.core.access import require_animal_access
from app.core.timezone import TARGET_TZ, ensure_utc
from app.services.daily_summary import get_target_date_bounds
from app.services.telemetry_quality import eligible_clause

router = APIRouter(prefix="/activity", tags=["activity"])


# Map legacy 4-class DB values → binary ML states
_LEGACY_TO_BINARY = {
    "lying": "Resting", "standing": "Resting",
    "walking": "Active", "running": "Active",
    "Active": "Active", "Resting": "Resting",
}


def _normalize_state(raw: str | None) -> str | None:
    """Collapse any activity_state value into Active or Resting."""
    if raw is None:
        return None
    return _LEGACY_TO_BINARY.get(raw)


def _build_budget(records: list[Telemetry]) -> ActivityBudget:
    """
    Compute time budget from a list of telemetry records.
    Each record contributes its actual accelerometer window duration.
    """
    # Prefer ML prediction (predicted_behavior) when available;
    # fall back to physical 4-class state (activity_state) otherwise.
    # _normalize_state converts both scales to the common binary reference.
    seconds_by_state: Counter[str] = Counter()
    for record in records:
        state = _normalize_state(record.predicted_behavior or record.activity_state)
        if not state:
            continue
        sample_rate = float(record.sample_rate or 0)
        window_samples = float(record.window_samples or 0)
        duration = window_samples / sample_rate if sample_rate > 0 and window_samples > 0 else 5.0
        seconds_by_state[state] += duration

    total_seconds = sum(seconds_by_state.values()) or 1.0

    def build_item(state: str) -> ActivityBudgetItem:
        seconds = seconds_by_state.get(state, 0.0)
        minutes = round(seconds / 60, 1)
        pct = round((seconds / total_seconds) * 100, 1)
        return ActivityBudgetItem(minutes=minutes, percentage=pct)

    return ActivityBudget(
        Active=build_item("Active"),
        Resting=build_item("Resting"),
    )


def _build_hourly(records: list[Telemetry]) -> list[HourlyBreakdown]:
    """
    Group telemetry records by hour and compute dominant state + avg activity.
    """
    from collections import defaultdict

    buckets: dict[int, list[Telemetry]] = defaultdict(list)
    for r in records:
        local_hour = ensure_utc(r.time).astimezone(TARGET_TZ).hour
        buckets[local_hour].append(r)

    result = []
    for hour in range(24):
        recs = buckets.get(hour, [])
        if not recs:
            result.append(HourlyBreakdown(
                hour=hour,
                dominant_state=None,
                avg_activity=0.0,
                record_count=0,
            ))
            continue

        resolved        = [r.predicted_behavior or r.activity_state for r in recs]
        states          = [_normalize_state(s) for s in resolved if s]
        dominant        = Counter(states).most_common(1)[0][0] if states else None
        activities      = [float(r.activity) for r in recs if r.activity is not None]
        avg_act         = round(sum(activities) / len(activities), 3) if activities else 0.0

        result.append(HourlyBreakdown(
            hour=hour,
            dominant_state=dominant,
            avg_activity=avg_act,
            record_count=len(recs),
        ))

    return result


# ============================================================
# GET /api/v1/activity/summary/{animal_id} (JWT mandatory, farm-scoped)
# ============================================================

@router.get("/summary/{animal_id}", response_model=ActivitySummary)
def get_activity_summary(
    animal_id: int,
    target_date: Optional[date] = Query(
        None,
        description="Date to summarize (YYYY-MM-DD). Defaults to today."
    ),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Daily activity budget for one animal.
    Requires view_animals permission on the animal's farm.
    """
    # Farm access check
    animal = require_animal_access(current_user, animal_id, "view_animals", db)

    target_date = target_date or datetime.now(TARGET_TZ).date()
    day_start, day_end_inclusive = get_target_date_bounds(target_date)
    day_end = day_end_inclusive + timedelta(microseconds=1)

    records = (
        db.query(Telemetry)
        .filter(
            Telemetry.animal_id == animal_id,
            Telemetry.time >= day_start,
            Telemetry.time <  day_end,
            eligible_clause(),
        )
        .order_by(Telemetry.time.asc())
        .all()
    )

    if not records:
        raise HTTPException(
            status_code=404,
            detail=f"No telemetry data for animal {animal_id} on {target_date}"
        )

    # Averages
    activities   = [float(r.activity)    for r in records if r.activity    is not None]
    temperatures = [float(r.temperature) for r in records if r.temperature is not None]
    batteries    = [int(r.battery_level) for r in records if r.battery_level is not None]

    averages = ActivityAverages(
        activity    = round(sum(activities)   / len(activities),    3) if activities   else 0.0,
        temperature = round(sum(temperatures) / len(temperatures),  2) if temperatures else None,
        battery     = round(sum(batteries)    / len(batteries))        if batteries    else None,
    )

    # Time coverage
    if len(records) > 1:
        duration_hours = round(
            (records[-1].time - records[0].time).total_seconds() / 3600, 2
        )
    else:
        duration_hours = 0.0

    return ActivitySummary(
        animal_id=animal_id,
        animal_name=animal.name,
        date=target_date,
        total_records=len(records),
        duration_hours=duration_hours,
        budget=_build_budget(records),
        averages=averages,
        hourly_breakdown=_build_hourly(records),
    )


# ============================================================
# GET /api/v1/activity/weekly/{animal_id} (JWT mandatory, farm-scoped)
# ============================================================

@router.get("/weekly/{animal_id}")
def get_weekly_summary(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    7-day activity trend for one animal.
    Requires view_animals permission on the animal's farm.
    """
    # Farm access check
    animal = require_animal_access(current_user, animal_id, "view_animals", db)

    today  = datetime.now(TARGET_TZ).date()
    result = []

    for offset in range(6, -1, -1):
        target_date = today - timedelta(days=offset)
        day_start, day_end_inclusive = get_target_date_bounds(target_date)
        day_end = day_end_inclusive + timedelta(microseconds=1)

        records = (
            db.query(Telemetry)
            .filter(
                Telemetry.animal_id == animal_id,
                Telemetry.time >= day_start,
                Telemetry.time <  day_end,
                eligible_clause(),
            )
            .all()
        )

        if records:
            result.append({
                "date":          target_date.isoformat(),
                "total_records": len(records),
                "budget":        _build_budget(records),
            })
        else:
            result.append({
                "date":          target_date.isoformat(),
                "total_records": 0,
                "budget":        None,
            })

    return result
