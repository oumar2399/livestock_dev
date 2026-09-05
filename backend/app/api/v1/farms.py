"""
Farms API - Farm-scoped CRUD
GET  /farms            → List user's farms (via membership)
POST /farms            → Create farm + auto-membership owner
GET  /farms/{id}       → Farm details (membership required)
PUT  /farms/{id}       → Update farm (manage_farm permission)
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

from app.db.database import get_db
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.user import User
from app.core.dependencies import get_current_user
from app.core.access import (
    get_accessible_farm_ids,
    require_farm,
    is_platform_admin,
    effective_permissions,
)

router = APIRouter(prefix="/farms", tags=["farms"])


# ─── Schemas ──────────────────────────────────────────────────────────────────

class FarmCreate(BaseModel):
    name: str
    address: Optional[str] = None
    size_hectares: Optional[float] = None

class FarmUpdate(BaseModel):
    name: str
    address: Optional[str] = None
    size_hectares: Optional[float] = None

class FarmResponse(BaseModel):
    id: int
    name: str
    address: Optional[str]
    size_hectares: Optional[float]
    owner_id: Optional[int]
    created_at: Optional[datetime] = None
    membership_role: Optional[str] = None
    permissions: List[str] = Field(default_factory=list)

    class Config:
        from_attributes = True


# ─── GET /farms (list user's farms) ──────────────────────────────────────────

@router.get("/", response_model=List[FarmResponse])
def list_farms(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """List farms the user has access to (via active membership)."""
    accessible = get_accessible_farm_ids(current_user, db)
    if not accessible:
        return []
    farms = db.query(Farm).filter(Farm.id.in_(accessible)).order_by(Farm.name).all()

    memberships = {}
    if not is_platform_admin(current_user):
        memberships = {
            membership.farm_id: membership
            for membership in db.query(FarmMembership).filter(
                FarmMembership.user_id == current_user.id,
                FarmMembership.farm_id.in_(accessible),
                FarmMembership.status == "active",
            ).all()
        }

    result = []
    for farm in farms:
        membership = memberships.get(farm.id)
        result.append({
            "id": farm.id,
            "name": farm.name,
            "address": farm.address,
            "size_hectares": farm.size_hectares,
            "owner_id": farm.owner_id,
            "created_at": farm.created_at,
            "membership_role": "admin" if is_platform_admin(current_user) else membership.role,
            "permissions": effective_permissions(current_user, farm.id, db),
        })
    return result


# ─── POST /farms (create + auto-membership) ──────────────────────────────────

@router.post("/", response_model=FarmResponse, status_code=201)
def create_farm(
    data: FarmCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Create a new farm. The creating user automatically becomes
    an owner member with active status.
    """
    farm = Farm(
        owner_id=current_user.id,
        name=data.name,
        address=data.address,
        size_hectares=data.size_hectares,
    )
    db.add(farm)
    db.flush()  # Get farm.id before creating membership

    # Auto-membership: owner / active
    membership = FarmMembership(
        user_id=current_user.id,
        farm_id=farm.id,
        role="owner",
        status="active",
    )
    db.add(membership)
    db.commit()
    db.refresh(farm)
    return farm


# ─── GET /farms/{id} (membership required) ───────────────────────────────────

@router.get("/{farm_id}", response_model=FarmResponse)
def get_farm(
    farm_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get farm details — requires active membership."""
    farm = require_farm(current_user, farm_id, None, db)
    return farm


# ─── PUT /farms/{id} (manage_farm permission) ────────────────────────────────

@router.put("/{farm_id}", response_model=FarmResponse)
def update_farm(
    farm_id: int,
    data: FarmUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Update farm — requires manage_farm permission."""
    farm = require_farm(current_user, farm_id, "manage_farm", db)

    farm.name = data.name
    if data.address is not None:
        farm.address = data.address
    if data.size_hectares is not None:
        farm.size_hectares = data.size_hectares

    db.commit()
    db.refresh(farm)
    return farm
