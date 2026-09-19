"""
Device schemas - Pydantic models for API serialization
"""
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator
from typing import Optional, Literal
from datetime import datetime

from app.core.binary_protocol import TRANSPORT_ID_MAX, TRANSPORT_ID_MIN
from app.core.security import valid_device_secret


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

    model_config = ConfigDict(from_attributes=True)


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
