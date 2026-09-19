"""Validated binary v3 input and lossless archive acknowledgement."""

from datetime import datetime
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class UntimedTelemetryCreate(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)
    session_id: int = Field(ge=1, le=2**63 - 1)
    sequence: int = Field(ge=0, le=2**32 - 1)
    window_end_elapsed_ms: int = Field(ge=15000, le=2**32 - 1)
    time_uncertainty_reason: Literal["never_synchronized", "holdover_expired", "clock_discontinuity", "non_monotonic_utc"]
    latitude: float | None = Field(ge=-90, le=90)
    longitude: float | None = Field(ge=-180, le=180)
    satellites: int = Field(ge=0, le=50)
    battery: int = Field(ge=0, le=100)
    sample_rate: Literal[10] = 10
    window_samples: Literal[150] = 150
    activity: float = Field(ge=0, le=20)
    activity_std: float = Field(ge=0, le=65.535)
    accel_x_mean: float = Field(ge=-6, le=6)
    accel_x_std: float = Field(ge=0, le=6)
    accel_x_min: float = Field(ge=-6, le=6)
    accel_x_max: float = Field(ge=-6, le=6)
    accel_y_mean: float = Field(ge=-6, le=6)
    accel_y_std: float = Field(ge=0, le=6)
    accel_y_min: float = Field(ge=-6, le=6)
    accel_y_max: float = Field(ge=-6, le=6)
    accel_z_mean: float = Field(ge=-6, le=6)
    accel_z_std: float = Field(ge=0, le=6)
    accel_z_min: float = Field(ge=-6, le=6)
    accel_z_max: float = Field(ge=-6, le=6)

    @model_validator(mode="after")
    def coherent_measurements(self):
        absent = self.latitude is None and self.longitude is None
        if (self.latitude is None) != (self.longitude is None) or (self.satellites == 0) != absent:
            raise ValueError("Inconsistent GPS fields")
        for axis in "xyz":
            if not getattr(self, f"accel_{axis}_min") <= getattr(self, f"accel_{axis}_mean") <= getattr(self, f"accel_{axis}_max"):
                raise ValueError("Expected min <= mean <= max")
        return self


class UntimedTelemetryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    device_id: str
    session_id: str
    sequence: int
    received_at: datetime
    protocol_version: Literal[3]
    measured_at: None = None
    time_reliable: Literal[False] = False
    classification_status: Literal["pending_model", "predicted", "excluded_context", "inference_failed"]

    @field_validator("id", "session_id", mode="before")
    @classmethod
    def lossless_identifier(cls, value):
        return str(value)
