"""
Telemetry API - Sensor data reception and consultation

Auth:
  POST /telemetry         → No auth (M5Stack is hardware)
  GET  /telemetry/latest  → JWT mandatory (farm-scoped)
  GET  /telemetry/history → JWT mandatory (farm-scoped)
  POST /telemetry/feedback→ JWT mandatory (farm-scoped)
"""
from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from app.db.database import get_db
from app.models.telemetry import Telemetry
from app.models.animal import Animal
from app.models.device import Device
from app.models.user import User
from app.models.feedback import PredictionFeedback
from app.schemas.telemetry import TelemetryCreate, TelemetryResponse, TelemetryLatest
from app.schemas.feedback import FeedbackCreate, FeedbackResponse
from app.core.dependencies import get_current_user
from app.core.access import (
    require_animal_access,
    resolve_farm_scope,
)
from app.services import ml_inference
from app.core.timezone import ensure_utc, to_utc_naive, utc_now
from app.api.v1.feedback import submit_prediction_feedback as upsert_prediction_feedback

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


# ─── Helper: auto-register or update device ───────────────────────────────────

def _sync_device(db: Session, device_id: str, farm_id: Optional[int], battery: int):
    """
    Auto-register a device on first telemetry, or update last_seen.
    Farm transfers are deliberately handled only by the authenticated device API.
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
        if device.farm_id != farm_id:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Device {device_id} belongs to farm {device.farm_id}, "
                    f"not farm {farm_id}"
                ),
            )
        # Re-activate if it was previously marked lost/retired
        if device.status in ("lost", "retired"):
            device.status = "active"


# ============================================================
# POST /api/v1/telemetry (NO AUTH — hardware)
# ============================================================

@router.post("/", response_model=TelemetryResponse, status_code=201)
async def receive_telemetry(
    data: TelemetryCreate,
    db: Session = Depends(get_db),
):
    """
    Receive M5Stack sensor data. No authentication required.
    Auto-registers the device in devices table on first contact.
    """
    # Find animal assigned to this device
    animal = db.query(Animal).filter(
        Animal.assigned_device == data.device_id,
        Animal.status == "active"
    ).first()

    if not animal:
        # Auto-register orphan device so admins can see it in the devices list
        _sync_device(db, data.device_id, farm_id=None, battery=data.battery)
        db.commit()
        logger.warning(f"📡 Orphan device {data.device_id} detected — telemetry discarded.")
        raise HTTPException(
            status_code=404,
            detail=f"No active animal assigned to device {data.device_id}. Device registered as orphan."
        )

    # Auto-register or refresh device (with farm_id drift correction)
    _sync_device(db, data.device_id, animal.farm_id, data.battery)

    # ── ML Prediction ──────────────────────────────────────────────────────────
    try:
        ml_prediction, confidence = ml_inference.predict_with_confidence(data.model_dump())
    except (ValueError, TypeError) as e:
        logger.warning(f"⚠️ ML inference skipped for device {data.device_id} (invalid/malformed features): {e}")
        ml_prediction, confidence = None, None
    except Exception as e:
        logger.error(f"❌ ML inference internal failure for device {data.device_id}: {e}", exc_info=True)
        ml_prediction, confidence = None, None

    # ── Activity state (physical 4-class) ────────────────────────────────────
    # Prefer the value sent by the collar firmware (lying/standing/walking/running).
    # Fall back to threshold-based estimation if the collar didn't send one.
    activity_state = data.activity_state or _calculate_activity_state(data.activity)

    # ── ML prediction (stored separately — never overwrites activity_state) ──
    if ml_prediction:
        predicted_behavior = ml_prediction
        behavior_confidence = confidence
        logger.info(f"🧠 ML prediction for {data.device_id}: {ml_prediction} ({confidence:.2%})")
    else:
        predicted_behavior = None
        behavior_confidence = None
        logger.info(f"📐 No ML prediction for {data.device_id} — activity_state={activity_state}")

    point_wkt = f"POINT({data.longitude} {data.latitude})"

    telemetry = Telemetry(
        time=ensure_utc(data.timestamp) if data.timestamp else utc_now(),
        animal_id=animal.id,
        device_id=data.device_id,
        location=point_wkt,
        latitude=data.latitude,
        longitude=data.longitude,
        altitude=data.altitude,
        speed=data.speed,
        satellites=data.satellites,

        # Activity
        activity=data.activity,
        activity_std=data.activity_std,
        activity_state=activity_state,
        predicted_behavior=predicted_behavior,
        behavior_confidence=behavior_confidence,

        # 3 axes
        accel_x_mean=data.accel_x_mean,
        accel_x_std=data.accel_x_std,
        accel_x_min=data.accel_x_min,
        accel_x_max=data.accel_x_max,

        accel_y_mean=data.accel_y_mean,
        accel_y_std=data.accel_y_std,
        accel_y_min=data.accel_y_min,
        accel_y_max=data.accel_y_max,

        accel_z_mean=data.accel_z_mean,
        accel_z_std=data.accel_z_std,
        accel_z_min=data.accel_z_min,
        accel_z_max=data.accel_z_max,

        # Metadata
        sample_rate=data.sample_rate,
        window_samples=data.window_samples,

        temperature=data.temperature,
        battery_level=data.battery,
        signal_strength=data.signal_strength,
    )

    db.add(telemetry)
    db.commit()
    db.refresh(telemetry)
    return telemetry


# ============================================================
# GET /api/v1/telemetry/latest (JWT mandatory, farm-scoped)
# ============================================================

@router.get("/latest", response_model=List[TelemetryLatest])
async def get_latest_telemetry(
    limit: int = Query(10, ge=1, le=100),
    animal_id: Optional[int] = Query(None),
    farm_id: Optional[int] = Query(None, description="Filter by farm"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Latest position for each animal — scoped to user's farms."""
    accessible = resolve_farm_scope(current_user, db, farm_id)

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
    ).filter(
        Animal.farm_id.in_(accessible)
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
            activity_state=_map_legacy_activity_state(t.activity_state),
            battery=t.battery_level,
            last_update=t.time,
        )
        for t, animal_name in results
    ]


# ============================================================
# GET /api/v1/telemetry/history/{animal_id} (JWT mandatory, farm-scoped)
# ============================================================

@router.get("/history/{animal_id}", response_model=List[TelemetryResponse])
async def get_telemetry_history(
    animal_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telemetry history for one animal — requires farm membership."""
    # Farm access check
    require_animal_access(current_user, animal_id, "view_animals", db)

    since = utc_now() - timedelta(hours=hours)

    results = db.query(Telemetry).filter(
        Telemetry.animal_id == animal_id,
        Telemetry.time >= since,
    ).order_by(Telemetry.time.asc()).all()

    # Map legacy states and attach existing prediction feedback
    def _norm_time(dt):
        if not dt:
            return None
        return to_utc_naive(dt).replace(microsecond=0)

    feedbacks = db.query(PredictionFeedback).filter(
        PredictionFeedback.animal_id == animal_id,
        PredictionFeedback.user_id == current_user.id,
    ).all()
    feedback_map = {_norm_time(fb.telemetry_time): fb for fb in feedbacks if fb.telemetry_time}

    for r in results:
        r.activity_state = _map_legacy_activity_state(r.activity_state)
        fb = feedback_map.get(_norm_time(r.time))
        if fb:
            r.has_feedback = True
            r.feedback_verdict = fb.verdict
            r.feedback_correction = fb.correction
        else:
            r.has_feedback = False
            r.feedback_verdict = None
            r.feedback_correction = None
        
    return results


# ─── Utility ──────────────────────────────────────────────────────────────────

def _calculate_activity_state(activity: float) -> str:
    """Map accelerometer value (g) to behavioral state."""
    if activity < 0.15: return "lying"
    if activity < 0.50: return "standing"
    if activity < 1.00: return "walking"
    return "running"

def _map_legacy_activity_state(state: Optional[str]) -> Optional[str]:
    """Map legacy 4-class states to the new binary Active/Resting states."""
    if state in ("walking", "running"):
        return "Active"
    elif state in ("standing", "lying"):
        return "Resting"
    return state


# ============================================================
# POST /api/v1/telemetry/feedback (JWT mandatory, farm-scoped)
# ============================================================

@router.post("/feedback", response_model=FeedbackResponse, status_code=201)
async def submit_prediction_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backward-compatible alias for the canonical idempotent feedback route."""
    return upsert_prediction_feedback(payload, db, current_user)
