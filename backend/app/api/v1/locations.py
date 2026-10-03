"""
Routes API pour la localisation et l'historique GPS (Lot B).

Auth: JWT mandatory, farm-scoped via require_farm / require_animal_access.
Permission: view_animals.

GET  /farms/{farm_id}/locations/latest               → positions de la ferme
GET  /farms/{farm_id}/locations/{animal_id}           → position courante d'un animal
GET  /farms/{farm_id}/locations/{animal_id}/history   → trajectoire segmentée
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from app.core.access import require_farm, require_animal_access
from app.core.dependencies import get_current_user
from app.core.timezone import utc_now, ensure_utc
from app.db.database import get_db
from app.models.user import User
from app.schemas.location import (
    LocationHistoryResponse,
    LocationPoint,
)
from app.services.location_service import (
    get_current_location,
    get_farm_locations,
    get_location_history,
)

router = APIRouter(prefix="/farms/{farm_id}/locations", tags=["locations"])


@router.get("/latest", response_model=list[LocationPoint])
def list_farm_locations(
    farm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Positions courantes de tous les animaux actifs de la ferme."""
    require_farm(current_user, farm_id, "view_animals", db)
    return get_farm_locations(db, farm_id)


@router.get("/{animal_id}", response_model=LocationPoint)
def get_animal_location(
    farm_id: int,
    animal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Position courante d'un animal spécifique."""
    animal = require_animal_access(current_user, animal_id, "view_animals", db)
    if animal.farm_id != farm_id:
        raise HTTPException(status_code=403, detail="Animal does not belong to this farm")

    location = get_current_location(db, animal, farm_id)
    if location is None:
        raise HTTPException(status_code=404, detail="No valid position available for this animal")
    return location


@router.get("/{animal_id}/history", response_model=LocationHistoryResponse)
def get_animal_location_history(
    farm_id: int,
    animal_id: int,
    start: Optional[datetime] = Query(None, description="Start of period (ISO 8601). Defaults to 24h ago."),
    end: Optional[datetime] = Query(None, description="End of period (ISO 8601). Defaults to now."),
    hours: Optional[int] = Query(None, ge=1, le=168, description="Shortcut: last N hours (overrides start)"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Historique de trajectoire avec segmentation par trous d'observation.

    Seules les positions prouvées par AnimalTrackingPeriod sont retournées.
    Les segments sont coupés lorsque le trou dépasse 30 minutes.
    """
    animal = require_animal_access(current_user, animal_id, "view_animals", db)
    if animal.farm_id != farm_id:
        raise HTTPException(status_code=403, detail="Animal does not belong to this farm")

    now = utc_now()

    if end is not None:
        end_utc = ensure_utc(end)
    else:
        end_utc = now

    if hours is not None:
        start_utc = end_utc - timedelta(hours=hours)
    elif start is not None:
        start_utc = ensure_utc(start)
    else:
        start_utc = end_utc - timedelta(hours=24)

    if start_utc >= end_utc:
        raise HTTPException(status_code=422, detail="start must be before end")

    return get_location_history(db, animal, farm_id, start_utc, end_utc)
