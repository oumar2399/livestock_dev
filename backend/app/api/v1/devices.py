"""
Devices API - Farm-scoped M5Stack sensor management

GET  /devices          → List devices (farm-scoped, orphans admin-only)
GET  /devices/{id}     → Single device (farm-scoped)
PATCH /devices/{id}    → Update status/notes/farm_id (with transfer logic)
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.database import get_db
from app.models.device import Device
from app.models.animal import Animal
from app.models.user import User
from app.schemas.device import DeviceResponse, DeviceUpdate
from app.core.dependencies import get_current_user
from app.core.access import (
    get_accessible_farm_ids,
    is_platform_admin,
    assert_device_visible,
    require_device_farm_patch,
    require_farm,
)

router = APIRouter(prefix="/devices", tags=["devices"])


# ─── GET /devices (JWT mandatory, farm-scoped) ───────────────────────────────

@router.get("/", response_model=List[DeviceResponse])
async def list_devices(
    farm_id: Optional[int] = Query(None, description="Filter by farm"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    List devices scoped to user's farms.
    Orphan devices (farm_id IS NULL) are visible to admin only.
    """
    accessible = get_accessible_farm_ids(current_user, db)

    query = db.query(Device)

    if farm_id is not None:
        # Explicit farm filter — must be accessible
        if farm_id not in accessible and not is_platform_admin(current_user):
            raise HTTPException(status_code=403, detail="Access denied to this farm")
        query = query.filter(Device.farm_id == farm_id)
    elif is_platform_admin(current_user):
        # Admin sees everything (including orphans)
        pass
    else:
        # Regular user sees only devices from their farms (no orphans)
        query = query.filter(Device.farm_id.in_(accessible))

    return query.order_by(Device.last_seen.desc().nullslast()).all()


# ─── GET /devices/{id} (JWT mandatory, farm-scoped) ─────────────────────────

@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Get a single device — must be in an accessible farm."""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    assert_device_visible(current_user, device, db)
    return device


# ─── PATCH /devices/{id} (JWT mandatory, permission-checked) ────────────────

@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update device status, notes, or farm_id.

    Farm transfer logic (§10b):
    - NULL → B : manage_devices on B (claim orphan)
    - A → B    : manage_devices on A AND B (transfer)
    - A → NULL : manage_devices on A (release)
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    # If farm_id is being changed, apply transfer permission logic
    if data.farm_id is not None or (data.farm_id is None and "farm_id" in (data.dict(exclude_unset=True))):
        new_farm_id = data.dict(exclude_unset=True).get("farm_id")
        if new_farm_id != device.farm_id:
            require_device_farm_patch(current_user, device, new_farm_id, db)
            assigned_animal = (
                db.query(Animal)
                .filter(Animal.assigned_device == device.id)
                .first()
            )
            if assigned_animal:
                raise HTTPException(
                    status_code=409,
                    detail=(
                        f"Device {device.id} is assigned to animal {assigned_animal.id}. "
                        "Unassign it before changing farms."
                    ),
                )
    else:
        # For non-farm_id updates, just check visibility
        assert_device_visible(current_user, device, db)
        # And manage_devices permission if changing status
        if data.status is not None and device.farm_id:
            require_farm(current_user, device.farm_id, "manage_devices", db)

    # Apply updates
    update_dict = data.dict(exclude_unset=True)
    if "status" in update_dict:
        allowed = {"active", "maintenance", "lost", "retired"}
        if update_dict["status"] not in allowed:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {allowed}")

    for field, value in update_dict.items():
        setattr(device, field, value)

    db.commit()
    db.refresh(device)
    return device
