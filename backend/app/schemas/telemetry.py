"""
Schémas Pydantic pour Telemetry - Données capteurs
"""
from pydantic import BaseModel, ConfigDict, Field, model_validator
from typing import Optional
from datetime import datetime


class TelemetryBase(BaseModel):
    device_id  : str   = Field(..., max_length=50)
    latitude   : float = Field(..., ge=-90,  le=90)
    longitude  : float = Field(..., ge=-180, le=180)
    altitude   : Optional[float] = Field(None, ge=-500, le=9000)
    speed      : Optional[float] = Field(None, ge=0, le=100)
    satellites : Optional[int]   = Field(None, ge=0, le=50)

    # Activité (rétrocompat — toujours présent)
    activity            : float           = Field(..., ge=0, le=20)
    activity_std        : Optional[float] = Field(None, ge=0)
    activity_state      : Optional[str]   = Field(None, max_length=20)
    predicted_behavior  : Optional[str]   = None
    behavior_confidence : Optional[float] = None

    # ── Accéléromètre 3 axes (NEW — tous optionnels) ────────
    accel_x_mean : Optional[float] = None
    accel_x_std  : Optional[float] = None
    accel_x_min  : Optional[float] = None
    accel_x_max  : Optional[float] = None

    accel_y_mean : Optional[float] = None
    accel_y_std  : Optional[float] = None
    accel_y_min  : Optional[float] = None
    accel_y_max  : Optional[float] = None

    accel_z_mean : Optional[float] = None
    accel_z_std  : Optional[float] = None
    accel_z_min  : Optional[float] = None
    accel_z_max  : Optional[float] = None

    # Metadata fenêtre (NEW — optionnel)
    sample_rate    : Optional[int] = None
    window_samples : Optional[int] = None
    # ────────────────────────────────────────────────────────

    temperature     : Optional[float] = Field(None, ge=35, le=45)
    battery         : int             = Field(..., ge=0, le=100)
    signal_strength : Optional[int]   = None


class TelemetryCreate(TelemetryBase):
    """
    Payload envoyé par M5Stack v2.0

    Exemple JSON minimal (rétrocompat v1.3) :
    {
      "device_id": "M5-001",
      "latitude": 34.6901,
      "longitude": 135.1955,
      "activity": 0.12,
      "battery": 78
    }

    Exemple JSON complet (v2.0 windowed) :
    {
      "device_id": "M5-001",
      "latitude": 34.6901,
      "longitude": 135.1955,
      "activity": 0.12,
      "activity_std": 0.03,
      "activity_state": "lying",
      "accel_x_mean": 0.02, "accel_x_std": 0.01,
      "accel_x_min": -0.01, "accel_x_max": 0.05,
      "accel_y_mean": -0.01, "accel_y_std": 0.01,
      "accel_y_min": -0.03, "accel_y_max": 0.02,
      "accel_z_mean": 1.00,  "accel_z_std": 0.02,
      "accel_z_min":  0.95,  "accel_z_max": 1.05,
      "sample_rate": 10,
      "window_samples": 50,
      "battery": 78
    }
    """
    timestamp: Optional[datetime] = None  # allows simulated historical data


class TelemetryResponse(TelemetryBase):
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    received_at: Optional[datetime] = None
    time_source: Optional[str] = None
    protocol_version: Optional[int] = None
    behavior_eligible: Optional[bool] = None
    exclusion_reason: Optional[str] = None
    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    time                : datetime
    animal_id           : Optional[int] = None
    battery             : int = Field(..., alias="battery_level",
                            serialization_alias="battery")
    has_feedback        : Optional[bool] = False
    feedback_verdict    : Optional[str] = None
    feedback_correction : Optional[str] = None

class BinaryTelemetryCreate(TelemetryCreate):
    latitude: Optional[float] = Field(None, ge=-90, le=90)
    longitude: Optional[float] = Field(None, ge=-180, le=180)

    @model_validator(mode="after")
    def coordinate_pair(self):
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("Coordinates must both be present or absent")
        return self


class TelemetryLatest(BaseModel):
    """Dernière position d'un animal (vue optimisée)"""
    animal_id   : int
    animal_name : str
    device_id   : str
    latitude    : Optional[float]
    longitude   : Optional[float]
    position_time: Optional[datetime] = None
    position_is_animal: bool = True
    device_status: Optional[str] = None
    behavior_eligible: Optional[bool] = None
    activity    : float
    activity_state : Optional[str] = None
    battery     : int
    last_update : datetime
