"""
Schémas Pydantic pour les notifications, tokens et préférences.
Compatible Pydantic v2.
"""
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel, Field, ConfigDict


class PushDeviceCreate(BaseModel):
    push_token: str = Field(..., min_length=1, max_length=255, description="Token push expo ou natif")
    provider: str = Field("expo", max_length=50)
    platform: Optional[str] = Field(None, max_length=50)


class PushDeviceResponse(BaseModel):
    id: int
    user_id: int
    provider: str
    push_token: str
    platform: Optional[str] = None
    active: bool
    created_at: datetime
    last_seen_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationPreferenceUpdate(BaseModel):
    farm_id: Optional[int] = Field(None, description="Ferme ciblée, ou null pour préférence globale")
    categories: Optional[List[str]] = Field(
        default=["geofence", "health", "battery", "offline"],
        description="Catégories d'alertes autorisées",
    )
    min_severity: Optional[str] = Field(
        default="info",
        pattern="^(info|warning|critical)$",
        description="Sévérité minimale (info, warning, critical)",
    )
    enabled: Optional[bool] = True


class NotificationPreferenceResponse(BaseModel):
    id: int
    user_id: int
    farm_id: Optional[int] = None
    categories: List[str]
    min_severity: str
    enabled: bool
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)


class NotificationDeliveryResponse(BaseModel):
    id: int
    alert_id: int
    farm_id: Optional[int] = None
    user_id: int
    channel: str
    event_type: str
    status: str
    attempt_count: int
    next_attempt_at: datetime
    last_error_code: Optional[str] = None
    provider_message_id: Optional[str] = None
    created_at: datetime
    sent_at: Optional[datetime] = None

    model_config = ConfigDict(from_attributes=True)


class DispatchResult(BaseModel):
    processed: int
    sent: int
    retry: int
    failed: int
    cancelled: int
