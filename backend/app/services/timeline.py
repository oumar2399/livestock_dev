"""Build a stable, cursor-paginated timeline from existing animal data."""

import base64
import json
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Iterable, Optional

from sqlalchemy import and_, false, or_
from sqlalchemy.orm import Session

from app.core.timezone import TARGET_TZ, UTC, ensure_utc
from app.models.alert import Alert
from app.models.daily_summary import DailyBehaviorSummary
from app.models.feedback import AlertFeedback, PredictionFeedback
from app.schemas.timeline import TimelineEventType, TimelineItem, TimelinePage


@dataclass(frozen=True)
class TimelineCursor:
    occurred_at: datetime
    event_type: str
    source_id: int


def encode_cursor(item: TimelineItem) -> str:
    payload = {
        "t": ensure_utc(item.occurred_at).isoformat(),
        "e": item.event_type.value,
        "i": item.source_id,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(value: str) -> TimelineCursor:
    try:
        padded = value + "=" * (-len(value) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded).decode("utf-8"))
        event_type = TimelineEventType(payload["e"]).value
        occurred_at = ensure_utc(datetime.fromisoformat(payload["t"]))
        source_id = int(payload["i"])
        if source_id <= 0:
            raise ValueError
        return TimelineCursor(occurred_at, event_type, source_id)
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Invalid timeline cursor") from exc


def _date_bounds(
    date_from: Optional[date],
    date_to: Optional[date],
) -> tuple[Optional[datetime], Optional[datetime]]:
    start = (
        datetime.combine(date_from, time.min, tzinfo=TARGET_TZ)
        .astimezone(UTC)
        .replace(tzinfo=None)
        if date_from
        else None
    )
    end = (
        datetime.combine(date_to + timedelta(days=1), time.min, tzinfo=TARGET_TZ)
        .astimezone(UTC)
        .replace(tzinfo=None)
        if date_to
        else None
    )
    return start, end


def _apply_bounds(query, column, start, end):
    if start:
        query = query.filter(column >= start)
    if end:
        query = query.filter(column < end)
    return query


def _apply_cursor(query, time_column, id_column, event_type, cursor):
    if cursor is None:
        return query

    cursor_time = cursor.occurred_at.replace(tzinfo=None)
    if event_type < cursor.event_type:
        same_time = time_column == cursor_time
    elif event_type == cursor.event_type:
        same_time = and_(time_column == cursor_time, id_column < cursor.source_id)
    else:
        same_time = false()
    return query.filter(or_(time_column < cursor_time, same_time))


def _alert_items(db, animal_id, start, end, cursor, fetch_limit):
    event_type = TimelineEventType.ALERT.value
    query = db.query(Alert).filter(Alert.animal_id == animal_id)
    query = _apply_bounds(query, Alert.triggered_at, start, end)
    query = _apply_cursor(query, Alert.triggered_at, Alert.id, event_type, cursor)
    rows = query.order_by(Alert.triggered_at.desc(), Alert.id.desc()).limit(fetch_limit)
    return [
        TimelineItem(
            id=f"alert:{row.id}",
            source_id=row.id,
            event_type=TimelineEventType.ALERT,
            occurred_at=ensure_utc(row.triggered_at),
            title=row.title or "Alert",
            summary=row.message,
            severity=row.severity,
            data={
                "alert_id": row.id,
                "alert_type": row.type,
                "acknowledged": row.acknowledged_at is not None,
                "resolved": row.resolved_at is not None,
            },
        )
        for row in rows
    ]


def _prediction_feedback_items(db, animal_id, start, end, cursor, fetch_limit):
    event_type = TimelineEventType.PREDICTION_FEEDBACK.value
    query = db.query(PredictionFeedback).filter(
        PredictionFeedback.animal_id == animal_id
    )
    query = _apply_bounds(query, PredictionFeedback.created_at, start, end)
    query = _apply_cursor(
        query,
        PredictionFeedback.created_at,
        PredictionFeedback.id,
        event_type,
        cursor,
    )
    rows = query.order_by(
        PredictionFeedback.created_at.desc(), PredictionFeedback.id.desc()
    ).limit(fetch_limit)
    return [
        TimelineItem(
            id=f"prediction_feedback:{row.id}",
            source_id=row.id,
            event_type=TimelineEventType.PREDICTION_FEEDBACK,
            occurred_at=ensure_utc(row.created_at),
            title="Prediction feedback",
            summary=row.verdict,
            data={
                "feedback_id": row.id,
                "verdict": row.verdict,
                "prediction": row.predicted_behavior,
                "correction": row.correction,
                "telemetry_time": (
                    ensure_utc(row.telemetry_time).isoformat()
                    if row.telemetry_time
                    else None
                ),
            },
        )
        for row in rows
    ]


def _alert_feedback_items(db, animal_id, start, end, cursor, fetch_limit):
    event_type = TimelineEventType.ALERT_FEEDBACK.value
    query = db.query(AlertFeedback).filter(AlertFeedback.animal_id == animal_id)
    query = _apply_bounds(query, AlertFeedback.created_at, start, end)
    query = _apply_cursor(
        query, AlertFeedback.created_at, AlertFeedback.id, event_type, cursor
    )
    rows = query.order_by(
        AlertFeedback.created_at.desc(), AlertFeedback.id.desc()
    ).limit(fetch_limit)
    return [
        TimelineItem(
            id=f"alert_feedback:{row.id}",
            source_id=row.id,
            event_type=TimelineEventType.ALERT_FEEDBACK,
            occurred_at=ensure_utc(row.created_at),
            title="Alert feedback",
            summary=row.verdict,
            data={
                "feedback_id": row.id,
                "alert_id": row.alert_id,
                "verdict": row.verdict,
                "notes": row.notes,
            },
        )
        for row in rows
    ]


def _daily_summary_items(db, animal_id, start, end, cursor, fetch_limit):
    event_type = TimelineEventType.DAILY_SUMMARY.value
    query = db.query(DailyBehaviorSummary).filter(
        DailyBehaviorSummary.animal_id == animal_id
    )
    query = _apply_bounds(query, DailyBehaviorSummary.created_at, start, end)
    query = _apply_cursor(
        query,
        DailyBehaviorSummary.created_at,
        DailyBehaviorSummary.id,
        event_type,
        cursor,
    )
    rows = query.order_by(
        DailyBehaviorSummary.created_at.desc(), DailyBehaviorSummary.id.desc()
    ).limit(fetch_limit)
    return [
        TimelineItem(
            id=f"daily_summary:{row.id}",
            source_id=row.id,
            event_type=TimelineEventType.DAILY_SUMMARY,
            occurred_at=ensure_utc(row.created_at),
            title="Daily activity summary",
            summary=f"Active {row.pct_active:.1f}% · Resting {row.pct_resting:.1f}%",
            data={
                "summary_id": row.id,
                "target_date": row.date.isoformat(),
                "pct_active": row.pct_active,
                "pct_resting": row.pct_resting,
                "n_predictions": row.n_predictions,
                "avg_confidence": row.avg_confidence,
            },
        )
        for row in rows
    ]


LOADERS = {
    TimelineEventType.ALERT: _alert_items,
    TimelineEventType.PREDICTION_FEEDBACK: _prediction_feedback_items,
    TimelineEventType.ALERT_FEEDBACK: _alert_feedback_items,
    TimelineEventType.DAILY_SUMMARY: _daily_summary_items,
}


def build_timeline(
    db: Session,
    animal_id: int,
    event_types: Optional[Iterable[TimelineEventType]],
    date_from: Optional[date],
    date_to: Optional[date],
    limit: int,
    cursor_value: Optional[str],
) -> TimelinePage:
    cursor = decode_cursor(cursor_value) if cursor_value else None
    start, end = _date_bounds(date_from, date_to)
    selected = set(event_types or LOADERS.keys())
    fetch_limit = limit + 1
    items: list[TimelineItem] = []

    for event_type, loader in LOADERS.items():
        if event_type in selected:
            items.extend(loader(db, animal_id, start, end, cursor, fetch_limit))

    items.sort(
        key=lambda item: (
            ensure_utc(item.occurred_at),
            item.event_type.value,
            item.source_id,
        ),
        reverse=True,
    )
    has_more = len(items) > limit
    page_items = items[:limit]
    next_cursor = encode_cursor(page_items[-1]) if has_more and page_items else None
    return TimelinePage(items=page_items, next_cursor=next_cursor)
