"""
Device schemas - Pydantic models for API serialization
"""
from pydantic import BaseModel, ConfigDict
from typing import Optional
from datetime import datetime


class DeviceResponse(BaseModel):
    id:               str
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
    status:  Optional[str] = None   # active / maintenance / lost / retired
    notes:   Optional[str] = None
    farm_id: Optional[int] = None
