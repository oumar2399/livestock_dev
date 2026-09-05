"""Farm-scoped geofence CRUD without automatic alert evaluation."""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.core.access import require_farm
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.geofence import Geofence
from app.models.user import User
from app.schemas.geofence import GeofenceCreate, GeofenceResponse, GeofenceUpdate
from app.services.geofence_service import (
    build_polygon,
    geofence_query,
    serialize_geofence,
)


router = APIRouter(prefix="/geofences", tags=["geofences"])


def _get_geofence_row(db: Session, geofence_id: int):
    row = geofence_query(db).filter(Geofence.id == geofence_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Geofence not found")
    return row


@router.get("/", response_model=list[GeofenceResponse])
def list_geofences(
    farm_id: int = Query(..., gt=0),
    active: Optional[bool] = Query(None),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_farm(current_user, farm_id, "view_animals", db)
    query = geofence_query(db).filter(Geofence.farm_id == farm_id)
    if active is not None:
        query = query.filter(Geofence.active == active)
    return [
        serialize_geofence(geofence, geojson)
        for geofence, geojson in query.order_by(Geofence.name, Geofence.id).all()
    ]


@router.get("/{geofence_id}", response_model=GeofenceResponse)
def get_geofence(
    geofence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    geofence, geojson = _get_geofence_row(db, geofence_id)
    require_farm(current_user, geofence.farm_id, "view_animals", db)
    return serialize_geofence(geofence, geojson)


@router.post("/", response_model=GeofenceResponse, status_code=201)
def create_geofence(
    payload: GeofenceCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    require_farm(current_user, payload.farm_id, "manage_farm", db)
    try:
        polygon = build_polygon(db, payload.points)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    geofence = Geofence(
        farm_id=payload.farm_id,
        name=payload.name,
        type=payload.type.value,
        active=payload.active,
        polygon=polygon,
    )
    db.add(geofence)
    db.commit()
    geofence, geojson = _get_geofence_row(db, geofence.id)
    return serialize_geofence(geofence, geojson)


@router.patch("/{geofence_id}", response_model=GeofenceResponse)
def update_geofence(
    geofence_id: int,
    payload: GeofenceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    geofence, _ = _get_geofence_row(db, geofence_id)
    require_farm(current_user, geofence.farm_id, "manage_farm", db)
    values = payload.model_dump(exclude_unset=True)

    if "points" in values:
        try:
            geofence.polygon = build_polygon(db, payload.points or [])
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
    if "name" in values:
        geofence.name = payload.name
    if "type" in values and payload.type is not None:
        geofence.type = payload.type.value
    if "active" in values:
        geofence.active = payload.active

    db.commit()
    geofence, geojson = _get_geofence_row(db, geofence_id)
    return serialize_geofence(geofence, geojson)


@router.delete("/{geofence_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_geofence(
    geofence_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    geofence, _ = _get_geofence_row(db, geofence_id)
    require_farm(current_user, geofence.farm_id, "manage_farm", db)
    db.delete(geofence)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
