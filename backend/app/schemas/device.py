"""
Device schemas - Pydantic models for API serialization
"""
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from typing import Optional, Literal
from datetime import datetime

import re

from app.core.binary_protocol import TRANSPORT_ID_MAX, TRANSPORT_ID_MIN

_DEVICE_ID_FORMAT = re.compile(r"[A-Z0-9_-]{3,50}")
from app.core.security import valid_device_secret


class AssignedAnimal(BaseModel):
    id: int
    name: str


class DevicePosition(BaseModel):
    latitude: float
    longitude: float
    time: datetime


class DeviceHealth(BaseModel):
    """Indicators only; the status "lost" is still confirmed by a human."""
    offline: bool
    offline_since: Optional[datetime] = None   # last reception; None if never seen
    last_fix_at: Optional[datetime] = None
    needs_attention: list[Literal["low_battery", "no_gps_fix", "battery_unknown"]] = []


class DeviceResponse(BaseModel):
    id:               str
    transport_id:     Optional[int] = None
    ingestion_revoked_at: Optional[datetime] = None
    farm_id:          Optional[int]
    model:            Optional[str]
    firmware_version: Optional[str]
    last_seen:        Optional[datetime]
    battery_capacity: Optional[int]
    status:           str
    notes:            Optional[str]
    created_at:       datetime
    assigned_animal:  Optional[AssignedAnimal] = None
    last_position:    Optional[DevicePosition] = None
    health:           Optional[DeviceHealth] = None

    model_config = ConfigDict(from_attributes=True)


class DeviceCreate(BaseModel):
    """Add a collar to a farm; the server picks the transport ID and the secret."""
    device_id: str = Field(..., min_length=3, max_length=50)
    farm_id: int = Field(..., gt=0)

    @field_validator("device_id")
    @classmethod
    def normalize_device_id(cls, value: str) -> str:
        value = value.strip().upper()
        if not _DEVICE_ID_FORMAT.fullmatch(value):
            raise ValueError("Device ID: 3 to 50 characters, letters A-Z, digits, '-' or '_'")
        return value


class DeviceProvisioned(DeviceResponse):
    """Creation answer: the only time the secret is ever returned."""
    device_secret: str


class DeviceUpdate(BaseModel):
    model_config = ConfigDict(hide_input_in_errors=True)

    status:  Optional[str] = None   # active / maintenance / lost / retired
    notes:   Optional[str] = None
    farm_id: Optional[int] = None
    transport_id: Optional[int] = Field(None, strict=True, ge=TRANSPORT_ID_MIN, le=TRANSPORT_ID_MAX)
    device_secret: Optional[SecretStr] = Field(None, json_schema_extra={"writeOnly": True})
    ingestion_action: Optional[Literal["revoke", "restore"]] = Field(None, json_schema_extra={"writeOnly": True})
    loss_started_at: Optional[datetime] = None
    confirm_remounted: bool = False

    @field_validator("ingestion_action", "loss_started_at")
    @classmethod
    def reject_null_action(cls, value):
        if value is None:
            raise ValueError("Omit this field instead of sending null")
        return value

    @field_validator("device_secret", mode="before")
    @classmethod
    def validate_secret(cls, value):
        if value is None:
            return value
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if not valid_device_secret(raw):
            raise ValueError("Device secret must contain 64 lowercase hexadecimal characters")
        return value
