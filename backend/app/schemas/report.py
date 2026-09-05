"""Schemas shared by research data exports."""

from datetime import datetime
from enum import Enum

from pydantic import BaseModel


class ReportDataset(str, Enum):
    TELEMETRY = "telemetry"
    DAILY_SUMMARIES = "daily_summaries"
    ALERTS = "alerts"
    PREDICTION_FEEDBACKS = "prediction_feedbacks"
    ALERT_FEEDBACKS = "alert_feedbacks"


class ReportPreview(BaseModel):
    dataset: ReportDataset
    columns: list[str]
    rows: list[list[str]]
    has_more: bool
    limit: int
    target_timezone: str
    generated_at: datetime
