from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import date


class ActivityBudgetItem(BaseModel):
    minutes: float
    percentage: float


class ActivityBudget(BaseModel):
    Active: ActivityBudgetItem
    Resting: ActivityBudgetItem


class ActivityAverages(BaseModel):
    activity: float
    temperature: Optional[float] = None
    battery: Optional[int] = None


class HourlyBreakdown(BaseModel):
    hour: int
    dominant_state: Optional[str] = None
    avg_activity: float
    record_count: int


class ActivitySummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    animal_id: int
    animal_name: str
    date: date
    total_records: int
    duration_hours: float
    budget: ActivityBudget
    averages: ActivityAverages
    hourly_breakdown: list[HourlyBreakdown]
