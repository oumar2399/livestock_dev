"""
Schémas Pydantic pour Alert - Alertes système
"""
from pydantic import BaseModel, Field
from typing import Optional, Dict, Any
from datetime import datetime
from enum import Enum

# ============================================================
# ENUMS (types fixes)
# ============================================================

class AlertType(str, Enum):
    """Types d'alertes possibles"""
    HEALTH = "health"
    GEOFENCE = "geofence"
    BATTERY = "battery"
    OFFLINE = "offline"
    CUSTOM = "custom"

class AlertSeverity(str, Enum):
    """Niveaux de gravité"""
    INFO = "info"
    WARNING = "warning"
    CRITICAL = "critical"

# ============================================================
# SCHÉMAS
# ============================================================

class AlertBase(BaseModel):
    """Base commune alertes"""
    animal_id: int = Field(..., gt=0)
    type: AlertType
    severity: AlertSeverity
    title: str = Field(..., max_length=255)
    message: Optional[str] = None
    alert_metadata: Optional[Dict[str, Any]] = None

class AlertCreate(AlertBase):
    """
    Création alerte (backend interne seulement)
    
    Exemple:
    {
      "animal_id": 1,
      "type": "health",
      "severity": "warning",
      "title": "Activité réduite",
      "message": "Activité 40% sous baseline depuis 6h",
      "metadata": {
        "current_activity": 0.6,
        "baseline": 1.0,
        "duration_hours": 6
      }
    }
    """
    pass

class AlertUpdate(BaseModel):
    """Mise à jour alerte (acquittement, résolution)"""
    acknowledged_at: Optional[datetime] = None
    acknowledged_by: Optional[int] = None
    resolved_at: Optional[datetime] = None

class AlertResponse(AlertBase):
    """Alerte renvoyée par API"""
    id: int
    triggered_at: datetime
    acknowledged_at: Optional[datetime] = None
    resolved_at: Optional[datetime] = None
    
    # Infos animal (jointure)
    animal_name: Optional[str] = None
    
    class Config:
        orm_mode = True

class AlertList(BaseModel):
    """Liste alertes avec filtres"""
    total: int
    alerts: list[AlertResponse]
    unresolved_count: int  # Nombre alertes non résolues