"""
Telemetry API - Sensor data reception and consultation

Auth:
  POST /telemetry         → No auth (M5Stack is hardware)
  GET  /telemetry/latest  → Optional auth
  GET  /telemetry/history → Optional auth
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta

from app.db.database import get_db
from app.models.telemetry import Telemetry
from app.models.animal import Animal
from app.models.device import Device
from app.schemas.telemetry import TelemetryCreate, TelemetryResponse, TelemetryLatest
from app.core.dependencies import get_current_user_optional

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


# ─── Helper: auto-register or update device ───────────────────────────────────

def _sync_device(db: Session, device_id: str, farm_id: int, battery: int):
    """
    Auto-register a device on first telemetry, or update last_seen.
    Called on every incoming telemetry record.
    """
    device = db.query(Device).filter(Device.id == device_id).first()

    if not device:
        # First contact — create device entry
        device = Device(
            id=device_id,
            farm_id=farm_id,
            model="M5Stack M5GO",
            firmware_version=None,
            last_seen=datetime.utcnow(),
            battery_capacity=battery,
            status="active",
        )
        db.add(device)
    else:
        # Known device — update tracking info
        device.last_seen        = datetime.utcnow()
        device.battery_capacity = battery
        # Re-activate if it was previously marked lost/retired
        if device.status in ("lost", "retired"):
            device.status = "active"


# ============================================================
# POST /api/v1/telemetry
# ============================================================

@router.post("/", response_model=TelemetryResponse, status_code=201)
async def receive_telemetry(
    data: TelemetryCreate,
    db: Session = Depends(get_db),
):
    """
    Receive M5Stack sensor data. No authentication required.

    Auto-registers the device in devices table on first contact.
    Updates last_seen + battery on every call.
    """
    # Find animal assigned to this device
    animal = db.query(Animal).filter(
        Animal.assigned_device == data.device_id,
        Animal.status == "active"
    ).first()

    if not animal:
        raise HTTPException(
            status_code=404,
            detail=f"No active animal assigned to device {data.device_id}"
        )

    # Auto-register or refresh device
    _sync_device(db, data.device_id, animal.farm_id, data.battery)

    activity_state = _calculate_activity_state(data.activity)
    point_wkt      = f"POINT({data.longitude} {data.latitude})"

    telemetry = Telemetry(
        time=datetime.utcnow(),
        animal_id=animal.id,
        device_id=data.device_id,
        location=point_wkt,
        latitude=data.latitude,
        longitude=data.longitude,
        altitude=data.altitude,
        speed=data.speed,
        satellites=data.satellites,
        activity=data.activity,
        activity_state=activity_state,
        temperature=data.temperature,
        battery_level=data.battery,
    )

    db.add(telemetry)
    db.commit()           # commits both telemetry and device upsert
    db.refresh(telemetry)
    return telemetry


# ============================================================
# GET /api/v1/telemetry/latest
# ============================================================

@router.get("/latest", response_model=List[TelemetryLatest])
async def get_latest_telemetry(
    limit: int = Query(10, ge=1, le=100),
    animal_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """Latest position for each animal. Used by the real-time map."""
    subquery = db.query(
        Telemetry.animal_id,
        func.max(Telemetry.time).label("last_time"),
    ).group_by(Telemetry.animal_id).subquery()

    query = db.query(
        Telemetry,
        Animal.name.label("animal_name"),
    ).join(
        Animal, Telemetry.animal_id == Animal.id
    ).join(
        subquery,
        (Telemetry.animal_id == subquery.c.animal_id)
        & (Telemetry.time == subquery.c.last_time),
    )

    if animal_id:
        query = query.filter(Telemetry.animal_id == animal_id)

    results = query.limit(limit).all()

    return [
        TelemetryLatest(
            animal_id=t.animal_id,
            animal_name=animal_name,
            device_id=t.device_id,
            latitude=float(t.latitude),
            longitude=float(t.longitude),
            activity=float(t.activity),
            battery=t.battery_level,
            last_update=t.time,
        )
        for t, animal_name in results
    ]


# ============================================================
# GET /api/v1/telemetry/history/{animal_id}
# ============================================================

@router.get("/history/{animal_id}", response_model=List[TelemetryResponse])
async def get_telemetry_history(
    animal_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user=Depends(get_current_user_optional),
):
    """Telemetry history for one animal. Used for activity charts."""
    animal = db.query(Animal).filter(Animal.id == animal_id).first()
    if not animal:
        raise HTTPException(status_code=404, detail="Animal not found")

    since = datetime.utcnow() - timedelta(hours=hours)

    return db.query(Telemetry).filter(
        Telemetry.animal_id == animal_id,
        Telemetry.time >= since,
    ).order_by(Telemetry.time.asc()).all()


# ─── Utility ──────────────────────────────────────────────────────────────────

def _calculate_activity_state(activity: float) -> str:
    """Map accelerometer value (g) to behavioral state."""
    if activity < 0.15: return "lying"
    if activity < 0.50: return "standing"
    if activity < 1.00: return "walking"
    return "running"