"""Device view for the app: assigned animal, last known position, health indicators.

Indicators only (Phase 3): "offline" and "needs attention" never change the device
status; "lost" is still confirmed by a human because it changes geofencing and
data-quality rules.

Positions and fixes are read only inside the tracking periods of the device's current
farm, so a collar moved between farms never reveals its previous farm's locations.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy.orm import Session

from app.core.config import (
    DEVICE_BATTERY_UNKNOWN_AFTER_MINUTES,
    DEVICE_LOW_BATTERY_PCT,
    DEVICE_NO_GPS_FIX_AFTER_MINUTES,
    DEVICE_OFFLINE_AFTER_MINUTES,
)
from app.core.timezone import ensure_utc, utc_now
from app.models.animal import Animal
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.services.provenance_service import proven_in_farm


def _farm_rows(db: Session, device: Device):
    query = db.query(Telemetry).filter(Telemetry.device_id == device.id)
    if device.farm_id is None:
        return None  # an unclaimed collar has no farm whose data it may show
    return query.filter(proven_in_farm(Telemetry.animal_id, Telemetry.time, device.farm_id))


def _latest(query, *conditions) -> Optional[Telemetry]:
    if query is None:
        return None
    return query.filter(*conditions).order_by(Telemetry.time.desc()).first()


def device_health(device: Device, last_fix: Optional[Telemetry], latest: Optional[Telemetry],
                  last_battery: Optional[Telemetry], now: datetime) -> dict:
    last_seen = ensure_utc(device.last_seen) if device.last_seen else None
    offline = last_seen is None or now - last_seen > timedelta(minutes=DEVICE_OFFLINE_AFTER_MINUTES)
    last_fix_at = ensure_utc(last_fix.time) if last_fix else None
    reasons: list[str] = []
    if device.status != "retired":
        if device.battery_capacity is not None and device.battery_capacity <= DEVICE_LOW_BATTERY_PCT:
            reasons.append("low_battery")
        # GPS and battery-reading checks only make sense while the collar is sending.
        if last_seen is not None and not offline:
            if last_fix_at is None or now - last_fix_at > timedelta(minutes=DEVICE_NO_GPS_FIX_AFTER_MINUTES):
                reasons.append("no_gps_fix")
            if latest is not None and latest.battery_level is None:
                last_reading = ensure_utc(last_battery.time) if last_battery else None
                if last_reading is None or now - last_reading > timedelta(minutes=DEVICE_BATTERY_UNKNOWN_AFTER_MINUTES):
                    reasons.append("battery_unknown")
    return {
        "offline": offline,
        "offline_since": last_seen if offline else None,
        "last_fix_at": last_fix_at,
        "needs_attention": reasons,
    }


def describe_device(db: Session, device: Device, now: Optional[datetime] = None) -> dict:
    """DeviceResponse fields plus assigned_animal, last_position and health."""
    now = now or utc_now()
    rows = _farm_rows(db, device)
    last_fix = _latest(rows, Telemetry.latitude.isnot(None), Telemetry.longitude.isnot(None))
    latest = _latest(rows)
    last_battery = _latest(rows, Telemetry.battery_level.isnot(None))
    animal = db.query(Animal).filter(Animal.assigned_device == device.id).first()
    return {
        **{column.name: getattr(device, column.name) for column in Device.__table__.columns
           if column.name != "device_secret"},
        "assigned_animal": {"id": animal.id, "name": animal.name} if animal else None,
        "last_position": ({"latitude": last_fix.latitude, "longitude": last_fix.longitude,
                           "time": ensure_utc(last_fix.time)} if last_fix else None),
        "health": device_health(device, last_fix, latest, last_battery, now),
    }
