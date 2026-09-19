"""
Telemetry API - Sensor data reception and consultation

Auth:
  POST /telemetry         → Device secret when provisioned; legacy JSON otherwise
  POST /telemetry/binary  → Provisioned device secret required
  GET  /telemetry/latest  → JWT mandatory (farm-scoped)
  GET  /telemetry/history → JWT mandatory (farm-scoped)
  POST /telemetry/feedback→ JWT mandatory (farm-scoped)
"""
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, Response
from sqlalchemy.orm import Session
from sqlalchemy import func, or_
from typing import List, Optional
from datetime import timedelta
from pydantic import ValidationError

from app.db.database import get_db
from app.models.telemetry import Telemetry
from app.models.animal import Animal
from app.models.device import Device
from app.models.user import User
from app.models.feedback import PredictionFeedback
from app.schemas.telemetry import TelemetryCreate, BinaryTelemetryCreate, TelemetryResponse, TelemetryLatest
from app.schemas.feedback import FeedbackCreate, FeedbackResponse
from app.schemas.untimed_telemetry import UntimedTelemetryCreate, UntimedTelemetryResponse
from app.core.dependencies import get_current_user
from app.core.access import (
    require_animal_access,
    resolve_farm_scope,
)
from app.services.telemetry_ingestion import ingest_telemetry
from app.services.untimed_telemetry import ingest_untimed
from app.services import binary_telemetry, ml_inference
from app.core import binary_protocol
from app.core.security import DEVICE_SECRET_HEADER, verify_device_secret
from app.core.timezone import to_utc_naive, utc_now
from app.services.telemetry_quality import eligible_clause
from app.api.v1.feedback import submit_prediction_feedback as upsert_prediction_feedback

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


def _authenticated_device(db: Session, secret: Optional[str], *, device_id=None, transport_id=None):
    key = Device.transport_id == transport_id if transport_id is not None else Device.id == device_id
    device = db.query(Device).filter(key).with_for_update().populate_existing().first()
    if device is not None and (device.ingestion_revoked_at is not None or device.status == "retired"):
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    if transport_id is not None and (device is None or device.device_secret is None):
        raise HTTPException(status_code=401, detail="Invalid device credentials")
    if device is not None and device.device_secret is not None:
        if not verify_device_secret(secret, device.device_secret):
            raise HTTPException(status_code=401, detail="Invalid device credentials")
    return device


async def read_binary_body(request: Request) -> bytes:
    request.state.binary_received_at = utc_now()
    if request.headers.get("content-type", "").split(";", 1)[0].strip().lower() != "application/octet-stream":
        raise HTTPException(status_code=415, detail="Expected application/octet-stream")
    if request.headers.get("content-encoding", "identity").lower() != "identity":
        raise HTTPException(status_code=415, detail="Encoded binary bodies are not supported")
    body = bytearray()
    async for chunk in request.stream():
        first = body[0] if body else (chunk[0] if chunk else None)
        maximum = binary_protocol.PACKET_SIZES.get(first, binary_protocol.PACKET_SIZE)
        if len(body) + len(chunk) > maximum:
            raise HTTPException(status_code=413, detail=f"Binary body exceeds {maximum} bytes")
        body.extend(chunk)
    try:
        binary_telemetry.read_binary_header(bytes(body))
    except binary_telemetry.BinaryProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    return bytes(body)


@router.post("/", response_model=TelemetryResponse, status_code=201)
def receive_telemetry(
    data: TelemetryCreate,
    db: Session = Depends(get_db),
    device_secret: Optional[str] = Header(None, alias=DEVICE_SECRET_HEADER),
):
    """Receive sensor data through the shared ingestion service."""
    _authenticated_device(db, device_secret, device_id=data.device_id)
    return ingest_telemetry(data, db).telemetry


@router.post(
    "/binary", response_model=TelemetryResponse | UntimedTelemetryResponse, status_code=201,
    responses={200: {"model": TelemetryResponse | UntimedTelemetryResponse}, 400: {"description": "Invalid binary envelope"},
               401: {"description": "Invalid device credentials"}, 409: {"description": "Measurement or model profile conflict"},
               413: {"description": "Body too large"}, 415: {"description": "Unsupported media type"},
               503: {"description": "Protocol disabled or model unavailable"}},
    openapi_extra={"requestBody": {"required": True, "content": {
        "application/octet-stream": {"schema": {"type": "string", "format": "binary"}}
    }}},
)
def receive_binary_telemetry(
    request: Request,
    response: Response,
    raw: bytes = Depends(read_binary_body),
    db: Session = Depends(get_db),
    device_secret: Optional[str] = Header(None, alias=DEVICE_SECRET_HEADER),
):
    """Authenticate first; v1/v2 are dated telemetry, v3 is a separate archive."""
    try:
        version, transport_id = binary_telemetry.read_binary_header(raw)
    except binary_telemetry.BinaryProtocolError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from None
    device = _authenticated_device(db, device_secret, transport_id=transport_id)
    if version == binary_protocol.UNTIMED_VERSION:
        try:
            data = UntimedTelemetryCreate(**binary_telemetry.decode_untimed_payload(raw))
        except (binary_telemetry.BinaryMeasurementError, ValidationError):
            raise HTTPException(422, "Invalid untimed binary measurements") from None
        result = ingest_untimed(data, raw, device.id, db, received_at=request.state.binary_received_at)
        response.status_code = 201 if result.created else 200
        return result.archive
    try:
        fields = binary_telemetry.decode_binary_payload(raw)
        binary_telemetry.validate_binary_timestamp(fields["timestamp"], request.state.binary_received_at)
        data = BinaryTelemetryCreate(device_id=device.id, **fields)
    except (binary_telemetry.BinaryMeasurementError, ValidationError) as exc:
        detail = str(exc) if isinstance(exc, binary_telemetry.BinaryMeasurementError) else "Invalid binary measurements"
        raise HTTPException(status_code=422, detail=detail) from None
    result = ingest_telemetry(data, db, idempotent=True, protocol_version=version,
                              received_at=request.state.binary_received_at)
    response.status_code = 201 if result.created else 200
    return result.telemetry

# ============================================================
# GET /api/v1/telemetry/latest (JWT mandatory, farm-scoped)
# ============================================================

@router.get("/latest", response_model=List[TelemetryLatest])
def get_latest_telemetry(
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
        eligible_clause(),
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

    results = query.order_by(Telemetry.animal_id).limit(limit).all()
    ids = [t.animal_id for t, _, _ in results]
    positions = {
        t.animal_id: (t, eligible)
        for t, eligible in db.query(Telemetry, eligible_clause())
        .outerjoin(Device, Device.id == Telemetry.device_id)
        .filter(Telemetry.animal_id.in_(ids), Telemetry.latitude.is_not(None),
                Telemetry.longitude.is_not(None), or_(eligible_clause(), Device.status == "lost"))
        .distinct(Telemetry.animal_id).order_by(Telemetry.animal_id, Telemetry.time.desc()).all()
    }
    devices = {d.id: d for d in db.query(Device).filter(Device.id.in_([t.device_id for t, _, _ in results])).all()}
    output = []
    for t, animal_name, eligible in results:
        position, position_eligible = positions.get(t.animal_id, (None, False))
        device = devices.get(t.device_id)
        is_lost = device is not None and device.status == "lost"
        output.append(TelemetryLatest(
            animal_id=t.animal_id,
            animal_name=animal_name,
            device_id=t.device_id,
            latitude=position.latitude if position else None,
            longitude=position.longitude if position else None,
            position_time=position.time if position else None,
            position_is_animal=bool(position_eligible and not is_lost),
            device_status=device.status if device else None,
            behavior_eligible=bool(eligible and not is_lost),
            activity=float(t.activity),
            activity_state=None if is_lost or not eligible else _map_legacy_activity_state(t.activity_state),
            battery=t.battery_level,
            last_update=t.time,
        ))
    return output


# ============================================================
# GET /api/v1/telemetry/history/{animal_id} (JWT mandatory, farm-scoped)
# ============================================================

@router.get("/history/{animal_id}", response_model=List[TelemetryResponse])
def get_telemetry_history(
    animal_id: int,
    hours: int = Query(24, ge=1, le=168),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Telemetry history for one animal — requires farm membership."""
    # Farm access check
    require_animal_access(current_user, animal_id, "view_animals", db)

    since = utc_now() - timedelta(hours=hours)

    results = db.query(Telemetry, eligible_clause()).filter(
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

    output = []
    for r, eligible in results:
        response = TelemetryResponse.model_validate(r)
        response.activity_state = _map_legacy_activity_state(r.activity_state)
        fb = feedback_map.get(_norm_time(r.time))
        if fb:
            response.has_feedback = True
            response.feedback_verdict = fb.verdict
            response.feedback_correction = fb.correction
        response.behavior_eligible = eligible
        if not eligible:
            response.exclusion_reason = r.exclusion_reason or "loss_period"
        output.append(response)
        
    return output


# ─── Utility ──────────────────────────────────────────────────────────────────


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
def submit_prediction_feedback(
    payload: FeedbackCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Backward-compatible alias for the canonical idempotent feedback route."""
    return upsert_prediction_feedback(payload, db, current_user)
