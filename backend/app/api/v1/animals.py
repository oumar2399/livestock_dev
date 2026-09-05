"""
Routes API Animals - CRUD animaux
Farm-scoped: all operations require active membership on the animal's farm.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from typing import List, Optional

from app.db.database import get_db
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.user import User
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

router = APIRouter(
    prefix="/animals",
    tags=["animals"]
)

# ============================================================
# GET /api/v1/animals - Liste animaux (farm-scoped)
# ============================================================

@router.get("/", response_model=AnimalList)
async def list_animals(
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
    animals = query.offset(offset).limit(page_size).all()

    # Build response with last telemetry
    animal_responses = []
    for animal in animals:
        last_telemetry = db.query(Telemetry).filter(
            Telemetry.animal_id == animal.id
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
async def get_animal(
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
        Telemetry.animal_id == animal_id
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
async def create_animal(
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

    create_data = animal_data.dict()
    create_data["assigned_device"] = validate_device_assignment(
        db,
        current_user,
        animal_data.farm_id,
        animal_data.assigned_device,
    )

    animal = Animal(**create_data)
    db.add(animal)
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
async def update_animal(
    animal_id: int,
    animal_data: AnimalUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update animal — requires edit_animals permission on the animal's farm.
    """
    animal = require_animal_access(current_user, animal_id, "edit_animals", db)

    update_data = animal_data.dict(exclude_unset=True)
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
async def delete_animal(
    animal_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Delete animal — requires edit_animals permission on the animal's farm.
    CASCADE deletes telemetry and alerts.
    """
    animal = require_animal_access(current_user, animal_id, "edit_animals", db)

    db.delete(animal)
    db.commit()

    return None  # 204 No Content
