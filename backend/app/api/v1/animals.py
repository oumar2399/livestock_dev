"""
Routes API Animals - CRUD animaux
Farm-scoped: all operations require active membership on the animal's farm.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import or_
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from app.db.database import get_db
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.device import Device
from app.models.farm import Farm
from app.models.daily_summary import DailyBehaviorSummary
from app.models.feedback import AlertFeedback, PredictionFeedback
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.veterinary import VeterinaryCase
from app.schemas.animal import (
    AnimalCreate,
    AnimalUpdate,
    AnimalResponse,
    AnimalList
)
from app.core.dependencies import (
    get_current_user,
    require_admin,
)
from app.core.access import (
    get_accessible_farm_ids,
    require_farm,
    require_animal_access,
    resolve_farm_scope,
)
from app.services.device_assignment import validate_device_assignment
from app.services.telemetry_quality import animal_position_clause
from app.services.provenance_service import record_tracking_period

router = APIRouter(
    prefix="/animals",
    tags=["animals"]
)

# ============================================================
# GET /api/v1/animals - Liste animaux (farm-scoped)
# ============================================================

@router.get("/", response_model=AnimalList)
def list_animals(
    farm_id: Optional[int] = Query(None, description="Filter by farm"),
    status: Optional[str] = Query(None, description="Filter by status"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(50, ge=1, le=100, description="Page size"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List animals — only those in farms the user has access to.
    """
    allowed_farm_ids = resolve_farm_scope(current_user, db, farm_id)

    # Base query — scoped to accessible farms
    query = db.query(Animal).filter(Animal.farm_id.in_(allowed_farm_ids))

    # Optional status filter
    if status:
        query = query.filter(Animal.status == status)

    # Total before pagination
    total = query.count()

    # Pagination
    offset = (page - 1) * page_size
    animals = query.order_by(Animal.id).offset(offset).limit(page_size).all()

    # Fetch only the latest position per animal on this page (PostgreSQL DISTINCT ON).
    latest_by_animal = {}
    if animals:
        latest_by_animal = {
            row.animal_id: row
            for row in db.query(
                Telemetry.animal_id, Telemetry.time, Telemetry.latitude, Telemetry.longitude
            )
            .filter(Telemetry.animal_id.in_([animal.id for animal in animals]))
            .filter(animal_position_clause())
            .distinct(Telemetry.animal_id)
            .order_by(Telemetry.animal_id, Telemetry.time.desc())
            .all()
        }

    # Build response with last telemetry
    animal_responses = []
    for animal in animals:
        last_telemetry = latest_by_animal.get(animal.id)

        animal_dict = {
            "id": animal.id,
            "farm_id": animal.farm_id,
            "name": animal.name,
            "official_id": animal.official_id,
            "species": animal.species,
            "breed": animal.breed,
            "sex": animal.sex,
            "birth_date": animal.birth_date,
            "weight": animal.weight,
            "photo_url": animal.photo_url,
            "assigned_device": animal.assigned_device,
            "status": animal.status,
            "created_at": animal.created_at,
            "updated_at": animal.updated_at,
            "last_latitude": last_telemetry.latitude if last_telemetry else None,
            "last_longitude": last_telemetry.longitude if last_telemetry else None,
            "last_update": last_telemetry.time if last_telemetry else None
        }

        animal_responses.append(AnimalResponse(**animal_dict))

    return AnimalList(
        total=total,
        animals=animal_responses,
        page=page,
        page_size=page_size
    )

# ============================================================
# GET /api/v1/animals/{animal_id} - Détail animal
# ============================================================

@router.get("/{animal_id}", response_model=AnimalResponse)
def get_animal(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Get animal details — requires membership on the animal's farm.
    """
    animal = require_animal_access(current_user, animal_id, "view_animals", db)

    # Last position
    last_telemetry = db.query(Telemetry).filter(
        Telemetry.animal_id == animal_id, animal_position_clause(),
    ).order_by(Telemetry.time.desc()).first()

    animal_dict = {
        "id": animal.id,
        "farm_id": animal.farm_id,
        "name": animal.name,
        "official_id": animal.official_id,
        "species": animal.species,
        "breed": animal.breed,
        "sex": animal.sex,
        "birth_date": animal.birth_date,
        "weight": animal.weight,
        "photo_url": animal.photo_url,
        "assigned_device": animal.assigned_device,
        "status": animal.status,
        "created_at": animal.created_at,
        "updated_at": animal.updated_at,
        "last_latitude": last_telemetry.latitude if last_telemetry else None,
        "last_longitude": last_telemetry.longitude if last_telemetry else None,
        "last_update": last_telemetry.time if last_telemetry else None
    }

    return AnimalResponse(**animal_dict)

# ============================================================
# POST /api/v1/animals - Créer animal
# ============================================================

@router.post("/", response_model=AnimalResponse, status_code=201)
def create_animal(
    animal_data: AnimalCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create animal — requires edit_animals permission on the target farm.
    """
    # Verify farm access with edit permission
    require_farm(current_user, animal_data.farm_id, "edit_animals", db)

    # Check official_id uniqueness
    if animal_data.official_id:
        existing = db.query(Animal).filter(
            Animal.official_id == animal_data.official_id
        ).first()
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Animal with official_id {animal_data.official_id} already exists"
            )

    create_data = animal_data.model_dump()
    create_data["assigned_device"] = validate_device_assignment(
        db,
        current_user,
        animal_data.farm_id,
        animal_data.assigned_device,
    )

    animal = Animal(**create_data)
    db.add(animal)
    db.flush()
    record_tracking_period(
        db=db,
        animal_id=animal.id,
        farm_id=animal.farm_id,
        device_id=animal.assigned_device,
        source="registration",
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Official ID or assigned device is already in use",
        ) from exc
    db.refresh(animal)

    return animal

# ============================================================
# PUT /api/v1/animals/{animal_id} - Modifier animal
# ============================================================

@router.put("/{animal_id}", response_model=AnimalResponse)
def update_animal(
    animal_id: int,
    animal_data: AnimalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update animal — requires edit_animals permission on the animal's farm.
    """
    animal = require_animal_access(current_user, animal_id, "edit_animals", db)

    old_device = animal.assigned_device
    old_farm = animal.farm_id

    update_data = animal_data.model_dump(exclude_unset=True)
    if "assigned_device" in update_data:
        update_data["assigned_device"] = validate_device_assignment(
            db,
            current_user,
            animal.farm_id,
            update_data["assigned_device"],
            current_animal_id=animal.id,
        )

    for field, value in update_data.items():
        setattr(animal, field, value)

    if animal.assigned_device != old_device or animal.farm_id != old_farm:
        record_tracking_period(
            db=db,
            animal_id=animal.id,
            farm_id=animal.farm_id,
            device_id=animal.assigned_device,
            source="farm_transfer" if animal.farm_id != old_farm else "device_reassignment",
        )

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409,
            detail="Official ID or assigned device is already in use",
        ) from exc
    db.refresh(animal)

    return animal

# ============================================================
# DELETE /api/v1/animals/{animal_id} - Supprimer animal
# ============================================================

@router.delete("/{animal_id}", status_code=204)
def delete_animal(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete animal — requires edit_animals permission on the animal's farm.
    Only empty records are deleted: an animal with any telemetry, alert, daily
    summary, feedback or veterinary case gets 409 "animal_has_history".
    Tracking periods alone do not count as history (one exists from registration).
    """
    animal = require_animal_access(current_user, animal_id, "edit_animals", db)

    history_tables = (Telemetry, Alert, DailyBehaviorSummary, PredictionFeedback,
                      AlertFeedback, VeterinaryCase)
    if any(db.query(model.animal_id).filter(model.animal_id == animal_id).first() is not None
           for model in history_tables):
        raise HTTPException(status_code=409, detail="animal_has_history")

    db.delete(animal)  # its tracking periods are removed by ON DELETE CASCADE
    db.commit()

    return None  # 204 No Content



# ============================================================
# POST /api/v1/animals/{animal_id}/transfer - Transfer (admin)
# ============================================================

class AnimalTransfer(BaseModel):
    target_farm_id: int = Field(..., gt=0)


@router.post("/{animal_id}/transfer", response_model=AnimalResponse)
def transfer_animal(
    animal_id: int,
    payload: AnimalTransfer,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_admin),
):
    """
    Move an animal to another farm (platform admin only), in one transaction:
    close the tracking period and open a new one (source 'farm_transfer'), move the
    collar with the animal, and resolve the previous farm's open alerts on it as
    "animal_transferred" (that farm can no longer act on them).
    Afterwards the receiving farm sees the animal's health history, not its past
    locations or the previous farm's geofence alerts (provenance_service).
    """
    animal = db.query(Animal).filter(Animal.id == animal_id).with_for_update().first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")
    target = db.get(Farm, payload.target_farm_id)
    if not target:
        raise HTTPException(status_code=404, detail="Farm not found")
    old_farm = animal.farm_id
    if target.id == old_farm:
        raise HTTPException(status_code=409, detail="The animal is already in this farm")

    now = datetime.utcnow()
    for alert in db.query(Alert).filter(
        Alert.animal_id == animal.id,
        Alert.resolved_at.is_(None),
        or_(Alert.farm_id == old_farm, Alert.farm_id.is_(None)),
    ).all():
        alert.resolved_at = now
        alert.alert_metadata = {**(alert.alert_metadata or {}),
                                "resolved_reason": "animal_transferred",
                                "transferred_to_farm_id": target.id}

    # The collar stays on the animal, so it moves with it.
    if animal.assigned_device:
        device = db.query(Device).filter(Device.id == animal.assigned_device).with_for_update().first()
        if device:
            device.farm_id = target.id

    animal.farm_id = target.id
    record_tracking_period(db=db, animal_id=animal.id, farm_id=target.id,
                           device_id=animal.assigned_device, source="farm_transfer")
    db.commit()
    db.refresh(animal)
    return animal
