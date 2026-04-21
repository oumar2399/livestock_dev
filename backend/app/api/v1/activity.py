"""
Activity Summary API - Behavioral analysis endpoints

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
from app.schemas.activity import (
    ActivitySummary, ActivityBudget, ActivityBudgetItem,
    ActivityAverages, HourlyBreakdown
)
from app.core.dependencies import get_current_user_optional

router = APIRouter(prefix="/activity", tags=["activity"])


def _build_budget(records: list[Telemetry]) -> ActivityBudget:
    """
    Compute time budget from a list of telemetry records.
    Each record represents one sampling window (~10s).
    Returns minutes and percentage per activity state.
    """
    counts = Counter(r.activity_state for r in records if r.activity_state)
    total  = sum(counts.values()) or 1  # avoid division by zero

    # Each record ≈ 10 seconds → convert to minutes
    seconds_per_record = 10

    def build_item(state: str) -> ActivityBudgetItem:
        n       = counts.get(state, 0)
        minutes = round((n * seconds_per_record) / 60, 1)
        pct     = round((n / total) * 100, 1)
        return ActivityBudgetItem(minutes=minutes, percentage=pct)

    return ActivityBudget(
        lying=build_item("lying"),
        standing=build_item("standing"),
        walking=build_item("walking"),
        running=build_item("running"),
    )


def _build_hourly(records: list[Telemetry]) -> list[HourlyBreakdown]:
    """
    Group telemetry records by hour and compute dominant state + avg activity.
    Returns a list of 24 HourlyBreakdown objects (missing hours filled with zeros).
    """
    from collections import defaultdict

    buckets: dict[int, list[Telemetry]] = defaultdict(list)
    for r in records:
        buckets[r.time.hour].append(r)

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

        states          = [r.activity_state for r in recs if r.activity_state]
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
# GET /api/v1/activity/summary/{animal_id}
# ============================================================

@router.get("/summary/{animal_id}", response_model=ActivitySummary)
async def get_activity_summary(
    animal_id: int,
    target_date: Optional[date] = Query(
        None,
        description="Date to summarize (YYYY-MM-DD). Defaults to today."
    ),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """
    Daily activity budget for one animal.
    Used by the mobile app pie chart (Budget Temps).

    Returns time spent in each state (lying / standing / walking / running)
    expressed in minutes and percentage, plus hourly breakdown.
    """
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")

    # Default to today if no date provided
    target_date = target_date or date.today()
    day_start   = datetime.combine(target_date, datetime.min.time())
    day_end     = day_start + timedelta(days=1)

    records = (
        db.query(Telemetry)
        .filter(
            Telemetry.animal_id == animal_id,
            Telemetry.time >= day_start,
            Telemetry.time <  day_end,
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
# GET /api/v1/activity/weekly/{animal_id}
# ============================================================

@router.get("/weekly/{animal_id}")
async def get_weekly_summary(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """
    7-day activity trend for one animal.
    Returns one budget per day — used for weekly trend charts.
    """
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")

    today  = date.today()
    result = []

    for offset in range(6, -1, -1):  # 6 days ago → today
        target_date = today - timedelta(days=offset)
        day_start   = datetime.combine(target_date, datetime.min.time())
        day_end     = day_start + timedelta(days=1)

        records = (
            db.query(Telemetry)
            .filter(
                Telemetry.animal_id == animal_id,
                Telemetry.time >= day_start,
                Telemetry.time <  day_end,
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