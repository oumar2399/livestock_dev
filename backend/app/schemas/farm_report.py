"""
Schémas Pydantic pour les rapports propriétaire et la qualité des données (Lot G & H).
"""
from __future__ import annotations

from datetime import date, datetime
from enum import Enum
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class FarmReportDataset(str, Enum):
    FARM_SUMMARY = "farm_summary"
    ANIMAL_QUALITY = "animal_quality"


class FarmCurrentState(BaseModel):
    generated_at: datetime
    total_animals: int
    animals_by_status: dict[str, int]
    total_devices: int
    devices_by_status: dict[str, int]
    assigned_devices_count: int
    unassigned_devices_count: int
    last_reception: Optional[dict[str, Any]] = None
    gps_freshness: Optional[dict[str, Any]] = None
    battery_summary: Optional[dict[str, Any]] = None
    active_alerts_count: int


class FarmPeriodSummary(BaseModel):
    date_from: date
    date_to: date
    effective_start: datetime
    effective_end: datetime
    provenance_available_from: Optional[datetime] = None
    scope_status: str
    dated_windows_count: int
    proven_tracking_seconds: float
    dated_coverage_seconds: float
    dated_coverage_ratio: Optional[float] = None
    behavioral_coverage_seconds: float
    behavioral_coverage_ratio: Optional[float] = None
    behavior_breakdown: dict[str, Any]
    gps_presence_ratio: Optional[float] = None
    behavioral_exclusions: dict[str, int]
    reception_delay: dict[str, Any]
    unobserved_gaps: dict[str, Any]
    alerts_triggered_in_period: int
    alerts_resolved_in_period: int
    limitations: list[str]


class FarmUntimedSummary(BaseModel):
    untimed_count: int
    breakdown_by_reason: dict[str, int]
    breakdown_by_attribution: dict[str, int]
    mandatory_label: str = "Archives reçues par les colliers rattachés à cette ferme à la réception"


class FarmOverviewResponse(BaseModel):
    farm_id: int
    farm_name: str
    generated_at: datetime
    target_timezone: str
    current_state: FarmCurrentState
    period_summary: FarmPeriodSummary
    untimed_summary: FarmUntimedSummary


class FarmQualityItem(BaseModel):
    animal_id: int
    animal_name: str
    date: date
    dated_windows_count: int
    covered_seconds: float
    coverage_ratio: Optional[float]
    active_count: int
    resting_count: int
    active_ratio: Optional[float]
    gps_presence_ratio: Optional[float]
    exclusions_count: int
    status: str


class FarmQualityResponse(BaseModel):
    farm_id: int
    farm_name: str
    generated_at: datetime
    target_timezone: str
    date_from: date
    date_to: date
    items: list[FarmQualityItem]


class FarmReportPreview(BaseModel):
    farm_id: int
    dataset: FarmReportDataset
    date_from: date
    date_to: date
    generated_at: datetime
    target_timezone: str
    columns: list[str]
    rows: list[list[str]]
    total_rows: int
    has_more: bool
    limit: int
