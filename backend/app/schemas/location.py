"""
Schémas Pydantic pour la localisation et l'historique GPS (Lot B).

LocationPoint      — position courante d'un animal
TrackPoint         — point individuel d'une trajectoire
TrackSegment       — segment continu de trajectoire
GapInfo            — trou d'observation entre segments
LocationHistoryResponse — réponse complète de l'historique
"""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class LocationPoint(BaseModel):
    """Position courante d'un animal, enrichie de la provenance et du statut matériel."""

    animal_id: int
    animal_name: str
    device_id: Optional[str] = None
    latitude: float = Field(..., ge=-90, le=90)
    longitude: float = Field(..., ge=-180, le=180)
    position_time: datetime
    position_is_animal: bool = True
    device_status: Optional[str] = None
    freshness: str  # "recent" | "stale" | "old"
    age_seconds: int


class TrackPoint(BaseModel):
    """Point individuel d'une trajectoire GPS."""

    latitude: float
    longitude: float
    time: datetime
    speed: Optional[float] = None
    satellites: Optional[int] = None
    is_reliable: bool = True


class TrackSegment(BaseModel):
    """Segment continu de trajectoire — aucun trou significatif interne."""

    points: list[TrackPoint]
    start_time: datetime
    end_time: datetime
    is_proven: bool = True
    quality: str = "reliable"  # "reliable" | "degraded" | "uncertain"


class GapInfo(BaseModel):
    """Trou d'observation entre deux segments."""

    start_time: datetime
    end_time: datetime
    duration_seconds: int
    reason: str  # "no_data" | "loss_period" | "unproven"


class LocationHistoryResponse(BaseModel):
    """Réponse complète de l'historique de localisation d'un animal."""

    animal_id: int
    animal_name: str
    device_id: Optional[str] = None
    position_is_animal: bool = True
    segments: list[TrackSegment]
    gaps: list[GapInfo]
    period_start: datetime
    period_end: datetime
    total_points: int
    proven_coverage_ratio: Optional[float] = None
