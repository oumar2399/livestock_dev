"""Authenticated, idempotent archive ingestion; never writes animal telemetry."""

import logging
import math
from dataclasses import dataclass

from fastapi import HTTPException
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.timezone import utc_now
from app.models.animal import Animal
from app.models.device import Device
from app.models.telemetry_quality import DeviceLossPeriod
from app.models.untimed_telemetry import UntimedTelemetry
from app.schemas.untimed_telemetry import UntimedTelemetryCreate
from app.services import ml_inference

logger = logging.getLogger(__name__)
PROFILE = (10, 150)


@dataclass(frozen=True)
class ArchiveResult:
    archive: UntimedTelemetry
    created: bool


def _lock_device(db, device_id):
    device = db.query(Device).filter_by(id=device_id).with_for_update().populate_existing().first()
    if (device is None or device.device_secret is None or device.ingestion_revoked_at is not None
            or device.status == "retired"):
        raise HTTPException(401, "Invalid device credentials")
    return device


def _classify(db, device, row, features):
    # UTC is unknown: even a closed loss period cannot be ruled out for this window.
    has_loss = db.query(DeviceLossPeriod.id).filter_by(device_id=device.id).first() is not None
    if device.status != "active" or row.device_status_at_reception != "active" or has_loss:
        row.classification_status = "excluded_context"
        row.exclusion_reason = "device_context_uncertain"
        return
    fingerprint = ml_inference.get_profile_fingerprint(PROFILE)
    if not ml_inference.profile_ready(PROFILE) or not fingerprint:
        row.classification_status = "pending_model"
        row.exclusion_reason = "model_unavailable"
        return
    try:
        label, confidence = ml_inference.predict_with_confidence(features)
        if label not in ("Active", "Resting") or confidence is None or not math.isfinite(confidence) or not 0 <= confidence <= 1:
            raise ValueError("Invalid prediction")
    except Exception:
        logger.warning("Untimed inference failed for device %s", device.id)
        row.classification_status = "inference_failed"
        row.exclusion_reason = "inference_failed"
        return
    row.classification_status = "predicted"
    row.exclusion_reason = None
    row.predicted_behavior = label
    row.behavior_confidence = confidence
    row.model_sha256 = fingerprint
    row.classified_at = utc_now()


def _existing(db, device_id, session_id, sequence):
    return db.query(UntimedTelemetry).filter_by(device_id=device_id, session_id=session_id, sequence=sequence).first()


def _reuse(row, raw):
    if bytes(row.raw_packet) != raw:
        raise HTTPException(409, "A different archive window already uses this identity")
    return ArchiveResult(row, False)


def ingest_untimed(data: UntimedTelemetryCreate, raw: bytes, device_id: str, db, *, received_at):
    device = _lock_device(db, device_id)
    existing = _existing(db, device_id, data.session_id, data.sequence)
    if existing is not None:
        return _reuse(existing, raw)
    if not settings.BINARY_V3_ENABLED:
        raise HTTPException(503, "Binary v3 is not enabled")
    animal_id = db.query(Animal.id).filter(
        Animal.assigned_device == device_id, Animal.status == "active",
    ).scalar()
    row = UntimedTelemetry(
        **data.model_dump(exclude={"battery"}), device_id=device_id,
        transport_id_at_reception=device.transport_id, battery_level=data.battery,
        protocol_version=3, measured_at=None, received_at=received_at, time_reliable=False,
        raw_packet=raw, farm_id_at_reception=device.farm_id, animal_id_at_reception=animal_id,
        device_status_at_reception=device.status, attribution_status="unknown",
    )
    _classify(db, device, row, data.model_dump())
    db.add(row)
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        if getattr(getattr(exc.orig, "diag", None), "constraint_name", None) != "uq_untimed_identity":
            raise
        _lock_device(db, device_id)
        existing = _existing(db, device_id, data.session_id, data.sequence)
        if existing is None:
            raise
        return _reuse(existing, raw)
    db.refresh(row)
    return ArchiveResult(row, True)


def classify_pending(db, *, limit=100):
    """Explicit bounded diagnostic retry; no replacement of existing predictions."""
    from app.core.binary_protocol import FEATURE_NAMES

    if not 1 <= limit <= 1000:
        raise ValueError("Limit must be between 1 and 1000")
    pending = ("pending_model", "inference_failed")
    candidates = db.query(UntimedTelemetry.id, UntimedTelemetry.device_id).filter(
        UntimedTelemetry.classification_status.in_(pending),
    ).order_by(UntimedTelemetry.id).limit(limit).all()
    results = {}
    for row_id, device_id in candidates:
        try:
            device = _lock_device(db, device_id)
        except HTTPException:
            db.rollback()
            results["access_blocked"] = results.get("access_blocked", 0) + 1
            continue
        row = db.query(UntimedTelemetry).filter(
            UntimedTelemetry.id == row_id, UntimedTelemetry.classification_status.in_(pending),
        ).with_for_update().populate_existing().first()
        if row is not None:
            features = {name: float(getattr(row, name)) for name in FEATURE_NAMES}
            _classify(db, device, row, {**features, "sample_rate": 10, "window_samples": 150})
            results[row.classification_status] = results.get(row.classification_status, 0) + 1
        db.commit()
    return results
