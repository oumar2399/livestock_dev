"""
Schémas Pydantic - Import centralisé
"""
from app.schemas.animal import (
    AnimalBase,
    AnimalCreate,
    AnimalUpdate,
    AnimalResponse,
    AnimalList
)
from app.schemas.telemetry import (
    TelemetryCreate,
    TelemetryResponse,
    TelemetryLatest
)
from app.schemas.alert import (
    AlertType,
    AlertSeverity,
    AlertCreate,
    AlertUpdate,
    AlertResponse,
    AlertList
)

__all__ = [
    # Animal
    "AnimalBase",
    "AnimalCreate",
    "AnimalUpdate",
    "AnimalResponse",
    "AnimalList",
    # Telemetry
    "TelemetryCreate",
    "TelemetryResponse",
    "TelemetryLatest",
    # Alert
    "AlertType",
    "AlertSeverity",
    "AlertCreate",
    "AlertUpdate",
    "AlertResponse",
    "AlertList",
]