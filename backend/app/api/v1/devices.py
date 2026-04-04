"""
Devices API - M5Stack sensor management

GET  /devices          → List all devices (from devices table)
GET  /devices/{id}     → Single device details
PATCH /devices/{id}    → Update status/notes (farmer/admin only)
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List

from app.db.database import get_db
from app.models.device import Device
from app.schemas.device import DeviceResponse, DeviceUpdate
from app.core.dependencies import get_current_user_optional, require_farmer

router = APIRouter(prefix="/devices", tags=["devices"])


# ─── GET /devices ─────────────────────────────────────────────────────────────

@router.get("/", response_model=List[DeviceResponse])
async def list_devices(
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """
    List all registered M5Stack devices.
    Devices are auto-registered on first telemetry received.
    """
    return db.query(Device).order_by(Device.last_seen.desc().nullslast()).all()


# ─── GET /devices/{id} ────────────────────────────────────────────────────────

@router.get("/{device_id}", response_model=DeviceResponse)
async def get_device(
    device_id: str,
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """Get a single device by ID (ex: 'M5-001')"""
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")
    return device


# ─── PATCH /devices/{id} ──────────────────────────────────────────────────────

@router.patch("/{device_id}", response_model=DeviceResponse)
async def update_device(
    device_id: str,
    data: DeviceUpdate,
    db: Session = Depends(get_db),
    current_user=Depends(require_farmer),
):
    """
    Update device status or notes.
    Farmer/admin only.

    Useful for marking a device as lost, under maintenance, or retired.
    """
    device = db.query(Device).filter(Device.id == device_id).first()
    if not device:
        raise HTTPException(status_code=404, detail=f"Device {device_id} not found")

    if data.status is not None:
        allowed = {"active", "maintenance", "lost", "retired"}
        if data.status not in allowed:
            raise HTTPException(status_code=400, detail=f"Status must be one of: {allowed}")
        device.status = data.status

    if data.notes is not None:
        device.notes = data.notes

    db.commit()
    db.refresh(device)
    return device