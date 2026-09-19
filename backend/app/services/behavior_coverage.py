"""Observed-window coverage, without treating gaps or overlapping windows as data."""

from datetime import datetime, time, timedelta
from app.core.config import settings
from app.core.timezone import TARGET_TZ, ensure_utc
from app.models.telemetry import Telemetry
from app.services.telemetry_quality import eligible_clause


def covered_seconds(intervals):
    total = 0.0
    previous_end = None
    for start, end in sorted(intervals):
        if previous_end is not None:
            start = max(start, previous_end)
        if end > start:
            total += (end - start).total_seconds()
        previous_end = max(previous_end, end) if previous_end else end
    return total


def insufficient_coverage_days(db, animal_id, start_date, end_date):
    start = datetime.combine(start_date, time.min, tzinfo=TARGET_TZ)
    end = datetime.combine(end_date + timedelta(days=1), time.min, tzinfo=TARGET_TZ)
    rows = db.query(Telemetry.time, Telemetry.received_at, Telemetry.sample_rate,
                    Telemetry.window_samples, eligible_clause(), Telemetry.predicted_behavior).filter(
        Telemetry.animal_id == animal_id, Telemetry.time >= start, Telemetry.time < end,
    ).order_by(Telemetry.time).yield_per(1000)
    qualified_days = set()
    intervals = {}
    for stamp, received, rate, samples, eligible, prediction in rows:
        stamp = ensure_utc(stamp).astimezone(TARGET_TZ)
        day = stamp.date()
        if received is not None:
            qualified_days.add(day)
        if not eligible or prediction not in ("Active", "Resting"):
            continue
        duration = samples / rate if rate and samples and rate > 0 and samples > 0 else 0
        if duration <= 0:
            continue
        midnight = datetime.combine(day, time.min, tzinfo=TARGET_TZ)
        intervals.setdefault(day, []).append((max(midnight, stamp - timedelta(seconds=duration)), stamp))
    minimum = settings.ANOMALY_MIN_COVERAGE_SECONDS
    return {day for day in qualified_days if minimum is None or covered_seconds(intervals.get(day, [])) < minimum}
