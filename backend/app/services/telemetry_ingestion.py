"""Shared telemetry ingestion, preserving the legacy JSON behavior."""

from datetime import datetime
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional
import logging

from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError

from app.core.timezone import ensure_utc, utc_now
from app.models.animal import Animal
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.schemas.telemetry import TelemetryCreate
from app.services import ml_inference
from app.core.config import settings
from app.services.telemetry_quality import measurement_eligible

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class IngestionResult:
    telemetry: Telemetry
    created: bool


def _existing_measurement(db: Session, animal_id: int, data: TelemetryCreate):
    return db.query(Telemetry).filter(
        Telemetry.animal_id == animal_id,
        Telemetry.time == ensure_utc(data.timestamp),
    ).first()


def _reuse_measurement(existing: Telemetry, data: TelemetryCreate) -> IngestionResult:
    values = data.model_dump(exclude={"timestamp", "battery", "predicted_behavior", "behavior_confidence"})
    values["activity_state"] = data.activity_state or _calculate_activity_state(data.activity)
    values["battery_level"] = data.battery
    for name, value in values.items():
        scale = getattr(Telemetry.__table__.c[name].type, "scale", None)
        if value is not None and scale is not None:
            value = Decimal(str(value)).quantize(Decimal(1).scaleb(-scale), rounding=ROUND_HALF_UP)
        if getattr(existing, name) != value:
            raise HTTPException(status_code=409, detail="A different measurement already exists at this timestamp")
    return IngestionResult(existing, created=False)


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



def _calculate_activity_state(activity: float) -> str:
    """Map accelerometer value (g) to behavioral state."""
    if activity < 0.15: return "lying"
    if activity < 0.50: return "standing"
    if activity < 1.00: return "walking"
    return "running"


def ingest_telemetry(data: TelemetryCreate, db: Session, *, idempotent: bool = False,
                     protocol_version=None, received_at=None) -> IngestionResult:
    """Associate, classify and persist a validated telemetry measurement."""
    received_at = received_at or utc_now()
    if idempotent and data.timestamp is None:
        raise ValueError("Idempotent ingestion requires a measurement timestamp")
    device = db.query(Device).filter(Device.id == data.device_id).with_for_update().populate_existing().first()
    if device is not None and (device.ingestion_revoked_at is not None or device.status == "retired"):
        raise HTTPException(401, "Invalid device credentials")
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

    if idempotent:
        existing = _existing_measurement(db, animal.id, data)
        if existing is not None:
            # No battery or last_seen rewind when an old measurement is replayed.
            return _reuse_measurement(existing, data)

    eligible = measurement_eligible(db, device, data.timestamp, data.sample_rate, data.window_samples)
    profile = (data.sample_rate, data.window_samples)
    if protocol_version == 2 and not settings.BINARY_V2_ENABLED:
        raise HTTPException(503, "Binary v2 is not enabled")
    if eligible and profile == (10, 150) and not ml_inference.profile_ready(profile):
        raise HTTPException(503, "The 15-second model is unavailable")
    if eligible and idempotent and profile == (10, 50):
        info = ml_inference.get_model_info()
        if info is not None and (info["target_freq"], info["window_samples"]) != profile:
            raise HTTPException(409, "Binary profile does not match the loaded model")

    # Auto-register or refresh the device without silently transferring farms.
    _sync_device(db, data.device_id, animal.farm_id, data.battery)

    # ── ML Prediction ──────────────────────────────────────────────────────────
    try:
        ml_prediction, confidence = (ml_inference.predict_with_confidence(data.model_dump())
                                     if eligible and profile in ((None, None), (10, 50), (10, 150))
                                     else (None, None))
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

    point_wkt = f"POINT({data.longitude} {data.latitude})" if data.latitude is not None else None

    telemetry = Telemetry(
        time=ensure_utc(data.timestamp) if data.timestamp else utc_now(),
        animal_id=animal.id,
        device_id=data.device_id,
        received_at=received_at,
        time_source="device_utc" if data.timestamp else "server_reception",
        protocol_version=protocol_version,
        behavior_eligible=eligible,
        exclusion_reason=None if eligible else "device_loss_or_uncertain_time",
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
    animal_id = animal.id
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint = getattr(getattr(exc.orig, "diag", None), "constraint_name", "") or ""
        if not (idempotent and getattr(exc.orig, "pgcode", None) == "23505"
                and (constraint == "telemetry_pkey" or constraint.endswith("_telemetry_pkey"))):
            raise
        existing = _existing_measurement(db, animal_id, data)
        if existing is None:
            raise
        return _reuse_measurement(existing, data)
    db.refresh(telemetry)
    return IngestionResult(telemetry, created=True)
