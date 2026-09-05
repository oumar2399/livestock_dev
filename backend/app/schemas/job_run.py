"""Pydantic schemas for daily pipeline execution history."""

from datetime import date, datetime
from typing import Literal, Optional

from pydantic import BaseModel


class DailyJobRunResponse(BaseModel):
    id: int
    job_name: str
    trigger_source: Literal["scheduled", "manual"]
    target_date: date
    timezone_name: str
    status: Literal["running", "success", "failed"]
    started_at: datetime
    finished_at: Optional[datetime] = None
    initiated_by: Optional[int] = None
    summaries_created: Optional[int] = None
    alerts_created: Optional[int] = None
    error_message: Optional[str] = None

    model_config = {"from_attributes": True}


class DailyJobRunList(BaseModel):
    total: int
    runs: list[DailyJobRunResponse]
    limit: int
    offset: int
