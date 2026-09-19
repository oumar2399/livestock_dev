"""
Devices API - Farm-scoped M5Stack sensor management

GET  /devices          → List devices (farm-scoped, orphans admin-only)
GET  /devices/{id}     → Single device (farm-scoped)
PATCH /devices/{id}    → Update status/notes/farm_id, provision or rotate credentials
"""
from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.routing import APIRoute
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from typing import List, Optional

from app.db.database import get_db
from app.models.device import Device
from app.models.animal import Animal
from app.models.user import User
from app.schemas.device import DeviceResponse, DeviceUpdate
from app.core.dependencies import get_current_user
from app.core.security import hash_device_secret, verify_device_secret
from app.core.timezone import utc_now
from app.services.telemetry_quality import update_loss_period
from app.core.access import (
    get_accessible_farm_ids,
    is_platform_admin,
    assert_device_visible,
    require_device_farm_patch,
    require_farm,
)

class DeviceRoute(APIRoute):
    """Keep credential input out of validation responses, including root errors."""

    def get_route_handler(self):
        handler = super().get_route_handler()

        async def guarded(request: Request):
            try:
                return await handler(request)
            except RequestValidationError as exc:
                if request.method != "PATCH":
                    raise
                errors = [
                    {key: error[key] for key in ("loc", "msg", "type")}
                    for error in exc.errors()
                ]
                return JSONResponse(status_code=422, content={"detail": errors})

        return guarded


router = APIRouter(prefix="/devices", tags=["devices"], route_class=DeviceRoute)


# ─── GET /devices (JWT mandatory, farm-scoped) ───────────────────────────────

@router.get("/", response_model=List[DeviceResponse])
def list_devices(
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
def get_device(
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
def update_device(
    device_id: str,
    data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Update device metadata or write-only credentials with farm permissions.

    Farm transfer logic (§10b):
    - NULL → B : manage_devices on B (claim orphan)
    - A → B    : manage_devices on A AND B (transfer)
    - A → NULL : manage_devices on A (release)
    """
    device = db.query(Device).filter(Device.id == device_id).with_for_update().populate_existing().first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    update_dict = data.model_dump(exclude_unset=True)
    new_farm_id = update_dict.get("farm_id", device.farm_id)
    if new_farm_id != device.farm_id:
        require_device_farm_patch(current_user, device, new_farm_id, db)
        assigned_animal = db.query(Animal).filter(Animal.assigned_device == device.id).first()
        if assigned_animal:
            raise HTTPException(
                status_code=409,
                detail=(f"Device {device.id} is assigned to animal {assigned_animal.id}. "
                        "Unassign it before changing farms."),
            )
    else:
        assert_device_visible(current_user, device, db)
        if {"status", "transport_id", "device_secret", "ingestion_action", "loss_started_at", "confirm_remounted"}.intersection(update_dict) and device.farm_id is not None:
            require_farm(current_user, device.farm_id, "manage_devices", db)

    if {"transport_id", "device_secret"}.intersection(update_dict):
        transport_id = update_dict.get("transport_id", device.transport_id)
        secret = update_dict.get("device_secret", device.device_secret)
        if device.device_secret is not None and (transport_id is None or secret is None):
            raise HTTPException(status_code=422, detail="Provisioned credentials cannot be cleared; rotate the secret instead")
        if (transport_id is None) != (secret is None):
            raise HTTPException(status_code=422, detail="Initial provisioning requires both transport_id and device_secret")
        if update_dict.get("device_secret") is not None:
            update_dict["device_secret"] = hash_device_secret(data.device_secret.get_secret_value())

    if "status" in update_dict:
        allowed = {"active", "maintenance", "lost", "retired"}
        if update_dict["status"] not in allowed:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {allowed}")

    action = update_dict.pop("ingestion_action", None)
    new_status = update_dict.get("status", device.status)
    if action == "restore":
        if new_status != "active" or data.device_secret is None:
            raise HTTPException(409, "Restore requires active status and a new secret")
        if device.device_secret and verify_device_secret(data.device_secret.get_secret_value(), device.device_secret):
            raise HTTPException(409, "Restore requires a different secret")
        if update_dict.get("transport_id", device.transport_id) is None:
            raise HTTPException(422, "Restore requires a transport ID")
        device.ingestion_revoked_at = None
    elif action == "revoke" or new_status == "retired":
        device.ingestion_revoked_at = device.ingestion_revoked_at or utc_now()

    update_loss_period(db, device, update_dict, current_user.id)

    for field, value in update_dict.items():
        setattr(device, field, value)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) == "uq_devices_transport_id":
            raise HTTPException(status_code=409, detail="Transport ID is already assigned") from None
        raise
    db.refresh(device)
    return device
