"""
Schémas Pydantic pour Telemetry - Données capteurs
"""
from pydantic import BaseModel, Field, validator
from typing import Optional
from datetime import datetime

class TelemetryBase(BaseModel):
    """Base commune données télémétrie"""
    device_id: str = Field(..., max_length=50)
    latitude: float = Field(..., ge=-90, le=90, description="Latitude (-90 à 90)")
    longitude: float = Field(..., ge=-180, le=180, description="Longitude (-180 à 180)")
    altitude: Optional[float] = Field(None, ge=-500, le=9000, description="Altitude en mètres")
    speed: Optional[float] = Field(None, ge=0, le=100, description="Vitesse en km/h")
    satellites: Optional[int] = Field(None, ge=0, le=50)
    activity: float = Field(..., ge=0, le=20, description="Activité en g")
    temperature: Optional[float] = Field(None, ge=35, le=45, description="Température °C")
    battery: int = Field(..., ge=0, le=100, description="Batterie %")

class TelemetryCreate(TelemetryBase):
    """
    Données envoyées par M5Stack
    
    Exemple JSON:
    {
      "device_id": "M5-001",
      "latitude": 48.856600,
      "longitude": 2.352200,
      "altitude": 35.2,
      "speed": 0.8,
      "satellites": 8,
      "activity": 1.23,
      "temperature": 38.5,
      "battery": 78
    }
    """
    pass

class TelemetryResponse(TelemetryBase):
    """Données renvoyées par API"""
    time: datetime
    animal_id: Optional[int] = None  # Peut être NULL si device pas assigné
    activity_state: Optional[str] = None
    
    class Config:
        orm_mode = True

class TelemetryLatest(BaseModel):
    """Dernière position d'un animal (vue optimisée)"""
    animal_id: int
    animal_name: str
    device_id: str
    latitude: float
    longitude: float
    activity: float
    battery: int
    last_update: datetime