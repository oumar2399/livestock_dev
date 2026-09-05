"""Stream stable, explicit research datasets as UTF-8 CSV."""

import csv
import io
import json
from datetime import date, datetime, time, timedelta
from decimal import Decimal
from typing import Iterable, Iterator, Optional, Sequence

from sqlalchemy.orm import Session

from app.core.config import TARGET_TIMEZONE
from app.core.timezone import TARGET_TZ, UTC, ensure_utc, utc_now
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.daily_summary import DailyBehaviorSummary
from app.models.farm import Farm
from app.models.feedback import AlertFeedback, PredictionFeedback
from app.models.telemetry import Telemetry
from app.models.user import User
from app.schemas.report import ReportDataset, ReportPreview


FORMULA_PREFIXES = ("=", "+", "-", "@")


def _target_bounds(
    date_from: Optional[date],
    date_to: Optional[date],
) -> tuple[Optional[datetime], Optional[datetime]]:
    start = (
        datetime.combine(date_from, time.min, tzinfo=TARGET_TZ).astimezone(UTC)
        if date_from
        else None
    )
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=TARGET_TZ)
        .astimezone(UTC)
        if date_to
        else None
    )
    return start, end


def _format_value(value):
    if value is None:
        return ""
    if isinstance(value, datetime):
        return ensure_utc(value).isoformat().replace("+00:00", "Z")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, Decimal):
        return format(value, "f")
    if isinstance(value, (dict, list)):
        value = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if isinstance(value, str) and value.startswith(FORMULA_PREFIXES):
        return f"'{value}"
    return value


def _csv_line(values: Sequence[object], include_bom: bool = False) -> str:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow([_format_value(value) for value in values])
    prefix = "\ufeff" if include_bom else ""
    return prefix + buffer.getvalue()


def _apply_naive_datetime_filters(query, column, start, end):
    if start:
        query = query.filter(column >= start.replace(tzinfo=None))
    if end:
        query = query.filter(column < end.replace(tzinfo=None))
    return query


def _bounded_rows(query, limit, batch_size):
    if limit is not None:
        query = query.limit(limit)
    return query.yield_per(min(limit, batch_size) if limit is not None else batch_size)


def _telemetry_rows(db, farm_id, animal_id, start, end, limit=None):
    query = (
        db.query(Telemetry, Animal.name, Animal.farm_id, Farm.name)
        .join(Animal, Animal.id == Telemetry.animal_id)
        .join(Farm, Farm.id == Animal.farm_id)
    )
    if farm_id is not None:
        query = query.filter(Animal.farm_id == farm_id)
    if animal_id is not None:
        query = query.filter(Telemetry.animal_id == animal_id)
    if start:
        query = query.filter(Telemetry.time >= start)
    if end:
        query = query.filter(Telemetry.time < end)

    for telemetry, animal_name, row_farm_id, farm_name in _bounded_rows(
        query.order_by(Telemetry.time, Telemetry.animal_id), limit, 1000
    ):
        yield (
            telemetry.time, row_farm_id, farm_name, telemetry.animal_id,
            animal_name, telemetry.device_id, telemetry.latitude,
            telemetry.longitude, telemetry.altitude, telemetry.speed,
            telemetry.satellites, telemetry.activity, telemetry.activity_std,
            telemetry.activity_state, telemetry.predicted_behavior,
            telemetry.behavior_confidence, telemetry.accel_x_mean,
            telemetry.accel_x_std, telemetry.accel_x_min, telemetry.accel_x_max,
            telemetry.accel_y_mean, telemetry.accel_y_std, telemetry.accel_y_min,
            telemetry.accel_y_max, telemetry.accel_z_mean, telemetry.accel_z_std,
            telemetry.accel_z_min, telemetry.accel_z_max, telemetry.sample_rate,
            telemetry.window_samples, telemetry.temperature,
            telemetry.battery_level, telemetry.signal_strength,
        )


def _daily_summary_rows(db, farm_id, animal_id, date_from, date_to, limit=None):
    query = (
        db.query(DailyBehaviorSummary, Animal.name, Animal.farm_id, Farm.name)
        .join(Animal, Animal.id == DailyBehaviorSummary.animal_id)
        .join(Farm, Farm.id == Animal.farm_id)
    )
    if farm_id is not None:
        query = query.filter(Animal.farm_id == farm_id)
    if animal_id is not None:
        query = query.filter(DailyBehaviorSummary.animal_id == animal_id)
    if date_from:
        query = query.filter(DailyBehaviorSummary.date >= date_from)
    if date_to:
        query = query.filter(DailyBehaviorSummary.date <= date_to)

    for summary, animal_name, row_farm_id, farm_name in _bounded_rows(
        query.order_by(DailyBehaviorSummary.date, DailyBehaviorSummary.animal_id), limit, 500
    ):
        yield (
            summary.date, row_farm_id, farm_name, summary.animal_id,
            animal_name, summary.pct_active, summary.pct_resting,
            summary.n_predictions, summary.avg_confidence, summary.created_at,
        )


def _alert_rows(db, farm_id, animal_id, start, end, resolved, limit=None):
    query = (
        db.query(Alert, Animal.name, Animal.farm_id, Farm.name)
        .join(Animal, Animal.id == Alert.animal_id)
        .join(Farm, Farm.id == Animal.farm_id)
    )
    if farm_id is not None:
        query = query.filter(Animal.farm_id == farm_id)
    if animal_id is not None:
        query = query.filter(Alert.animal_id == animal_id)
    query = _apply_naive_datetime_filters(query, Alert.triggered_at, start, end)
    if resolved is not None:
        query = query.filter(
            Alert.resolved_at.isnot(None) if resolved else Alert.resolved_at.is_(None)
        )

    for alert, animal_name, row_farm_id, farm_name in _bounded_rows(
        query.order_by(Alert.triggered_at, Alert.id), limit, 500
    ):
        yield (
            alert.id, alert.triggered_at, row_farm_id, farm_name,
            alert.animal_id, animal_name, alert.type, alert.severity,
            alert.title, alert.message, alert.acknowledged_at,
            alert.acknowledged_by, alert.resolved_at, alert.alert_metadata,
        )


def _prediction_feedback_rows(db, farm_id, animal_id, start, end, limit=None):
    query = (
        db.query(PredictionFeedback, Animal.name, Animal.farm_id, Farm.name, User.email)
        .join(Animal, Animal.id == PredictionFeedback.animal_id)
        .join(Farm, Farm.id == Animal.farm_id)
        .join(User, User.id == PredictionFeedback.user_id)
    )
    if farm_id is not None:
        query = query.filter(Animal.farm_id == farm_id)
    if animal_id is not None:
        query = query.filter(PredictionFeedback.animal_id == animal_id)
    query = _apply_naive_datetime_filters(
        query, PredictionFeedback.created_at, start, end
    )

    for feedback, animal_name, row_farm_id, farm_name, user_email in _bounded_rows(
        query.order_by(PredictionFeedback.created_at, PredictionFeedback.id), limit, 500
    ):
        yield (
            feedback.id, feedback.created_at, row_farm_id, farm_name,
            feedback.animal_id, animal_name, feedback.user_id, user_email,
            feedback.telemetry_time, feedback.predicted_behavior,
            feedback.confidence, feedback.verdict, feedback.correction,
        )


def _alert_feedback_rows(db, farm_id, animal_id, start, end, limit=None):
    query = (
        db.query(AlertFeedback, Animal.name, Animal.farm_id, Farm.name, User.email)
        .join(Animal, Animal.id == AlertFeedback.animal_id)
        .join(Farm, Farm.id == Animal.farm_id)
        .join(User, User.id == AlertFeedback.user_id)
    )
    if farm_id is not None:
        query = query.filter(Animal.farm_id == farm_id)
    if animal_id is not None:
        query = query.filter(AlertFeedback.animal_id == animal_id)
    query = _apply_naive_datetime_filters(query, AlertFeedback.created_at, start, end)

    for feedback, animal_name, row_farm_id, farm_name, user_email in _bounded_rows(
        query.order_by(AlertFeedback.created_at, AlertFeedback.id), limit, 500
    ):
        yield (
            feedback.id, feedback.created_at, row_farm_id, farm_name,
            feedback.animal_id, animal_name, feedback.user_id, user_email,
            feedback.alert_id, feedback.alert_type, feedback.z_score,
            feedback.verdict, feedback.notes,
        )


HEADERS = {
    ReportDataset.TELEMETRY: (
        "time_utc", "farm_id", "farm_name", "animal_id", "animal_name",
        "device_id", "latitude", "longitude", "altitude", "speed",
        "satellites", "activity", "activity_std", "activity_state",
        "predicted_behavior", "behavior_confidence", "accel_x_mean",
        "accel_x_std", "accel_x_min", "accel_x_max", "accel_y_mean",
        "accel_y_std", "accel_y_min", "accel_y_max", "accel_z_mean",
        "accel_z_std", "accel_z_min", "accel_z_max", "sample_rate",
        "window_samples", "temperature", "battery_level", "signal_strength",
    ),
    ReportDataset.DAILY_SUMMARIES: (
        "target_date", "farm_id", "farm_name", "animal_id", "animal_name",
        "pct_active", "pct_resting", "n_predictions", "avg_confidence",
        "created_at_utc",
    ),
    ReportDataset.ALERTS: (
        "alert_id", "triggered_at_utc", "farm_id", "farm_name", "animal_id",
        "animal_name", "type", "severity", "title", "message",
        "acknowledged_at_utc", "acknowledged_by", "resolved_at_utc",
        "alert_metadata_json",
    ),
    ReportDataset.PREDICTION_FEEDBACKS: (
        "feedback_id", "created_at_utc", "farm_id", "farm_name", "animal_id",
        "animal_name", "user_id", "user_email", "telemetry_time_utc",
        "predicted_behavior", "confidence", "verdict", "correction",
    ),
    ReportDataset.ALERT_FEEDBACKS: (
        "feedback_id", "created_at_utc", "farm_id", "farm_name", "animal_id",
        "animal_name", "user_id", "user_email", "alert_id", "alert_type",
        "z_score", "verdict", "notes",
    ),
}


def _dataset_rows(
    db: Session,
    dataset: ReportDataset,
    farm_id: Optional[int],
    animal_id: Optional[int],
    date_from: Optional[date],
    date_to: Optional[date],
    resolved: Optional[bool],
    limit: Optional[int] = None,
) -> Iterable[Sequence[object]]:
    start, end = _target_bounds(date_from, date_to)
    if dataset == ReportDataset.TELEMETRY:
        return _telemetry_rows(
            db, farm_id, animal_id, start, end, limit
        )
    elif dataset == ReportDataset.DAILY_SUMMARIES:
        return _daily_summary_rows(db, farm_id, animal_id, date_from, date_to, limit)
    elif dataset == ReportDataset.ALERTS:
        return _alert_rows(db, farm_id, animal_id, start, end, resolved, limit)
    elif dataset == ReportDataset.PREDICTION_FEEDBACKS:
        return _prediction_feedback_rows(db, farm_id, animal_id, start, end, limit)
    else:
        return _alert_feedback_rows(db, farm_id, animal_id, start, end, limit)


def preview_dataset(
    db: Session,
    dataset: ReportDataset,
    farm_id: Optional[int],
    animal_id: Optional[int],
    date_from: Optional[date],
    date_to: Optional[date],
    resolved: Optional[bool],
    limit: int = 20,
) -> ReportPreview:
    if not 1 <= limit <= 50:
        raise ValueError("Preview limit must be between 1 and 50")
    # One extra row detects truncation without a COUNT or an unbounded export.
    rows = list(_dataset_rows(db, dataset, farm_id, animal_id, date_from, date_to, resolved, limit + 1))
    return ReportPreview(
        dataset=dataset,
        columns=list(HEADERS[dataset]),
        rows=[[str(_format_value(value)) for value in row] for row in rows[:limit]],
        has_more=len(rows) > limit,
        limit=limit,
        target_timezone=TARGET_TIMEZONE,
        generated_at=utc_now(),
    )


def stream_dataset(
    db: Session,
    dataset: ReportDataset,
    farm_id: Optional[int],
    animal_id: Optional[int],
    date_from: Optional[date],
    date_to: Optional[date],
    resolved: Optional[bool],
) -> Iterator[str]:
    rows = _dataset_rows(db, dataset, farm_id, animal_id, date_from, date_to, resolved)

    yield _csv_line(HEADERS[dataset], include_bom=True)
    for row in rows:
        yield _csv_line(row)
