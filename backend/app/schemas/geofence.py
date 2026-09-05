"""Validated API contracts for farm geofences."""

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class GeofenceType(str, Enum):
    PASTURE = "pasture"
    DANGER = "danger"


class GeoPoint(BaseModel):
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)


class GeofenceCreate(BaseModel):
    farm_id: int = Field(..., gt=0)
    name: str = Field(..., min_length=1, max_length=255)
    type: GeofenceType
    active: bool = True
    points: list[GeoPoint] = Field(..., min_length=3)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class GeofenceUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    type: Optional[GeofenceType] = None
    active: Optional[bool] = None
    points: Optional[list[GeoPoint]] = Field(None, min_length=3)

    @field_validator("name")
    @classmethod
    def validate_name(cls, value: Optional[str]) -> Optional[str]:
        if value is None:
            return None
        value = value.strip()
        if not value:
            raise ValueError("name cannot be blank")
        return value


class GeofenceResponse(BaseModel):
    id: int
    farm_id: int
    name: str
    type: str
    active: bool
    points: list[GeoPoint]
    created_at: Optional[datetime] = None
