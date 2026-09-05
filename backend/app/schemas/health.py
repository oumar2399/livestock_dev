"""Schemas for public health probes and the admin system status."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, Field


class LivenessResponse(BaseModel):
    status: Literal["alive"] = "alive"
    checked_at: datetime


class ReadinessResponse(BaseModel):
    status: Literal["ready", "not_ready"]
    checked_at: datetime


class DatabaseHealth(BaseModel):
    status: Literal["up", "down"]
    latency_ms: Optional[float] = None


class ModelHealth(BaseModel):
    status: Literal["loaded", "unavailable"]
    classes: list[str] = Field(default_factory=list)


class SchemaHealth(BaseModel):
    revision: Optional[str] = None


class SchedulerHealth(BaseModel):
    enabled: bool
    running: bool
    next_run_at: Optional[datetime] = None


class SystemStatusResponse(BaseModel):
    status: Literal["healthy", "degraded", "unhealthy"]
    checked_at: datetime
    target_timezone: str
    database: DatabaseHealth
    model: ModelHealth
    schema_info: SchemaHealth = Field(alias="schema")
    scheduler: SchedulerHealth

    model_config = {"populate_by_name": True}
