"""Unified animal timeline API schemas."""

from datetime import datetime
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field


class TimelineEventType(str, Enum):
    ALERT = "alert"
    PREDICTION_FEEDBACK = "prediction_feedback"
    ALERT_FEEDBACK = "alert_feedback"
    DAILY_SUMMARY = "daily_summary"


class TimelineItem(BaseModel):
    id: str
    source_id: int
    event_type: TimelineEventType
    occurred_at: datetime
    title: str
    summary: Optional[str] = None
    severity: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)


class TimelinePage(BaseModel):
    items: list[TimelineItem]
    next_cursor: Optional[str] = None
