"""B.4 protocol compatibility, revocation and loss-period regression cases."""

import struct
from datetime import timedelta
import pytest

from app.core.config import settings
from app.core.security import generate_device_secret
from app.core.timezone import utc_now
from app.models.telemetry import Telemetry
from app.services import ml_inference
from app.services.binary_telemetry import decode_binary_payload, BinaryMeasurementError
from app.services.telemetry_quality import eligible_clause
from app.models.telemetry_quality import BehaviorRebuild, DeviceLossPeriod
from app.models.daily_summary import DailyBehaviorSummary
from app.models.membership import FarmMembership
from app.core.timezone import TARGET_TZ
from app.services.daily_summary import aggregate_daily_behavior
from app.services.telemetry_quality import process_behavior_rebuilds
from test_binary_protocol import REFERENCE
from test_binary_telemetry_api import headers, json_equivalent, URL


def packet(version=2, gps=True, stamp=None):
    raw = bytearray(REFERENCE)
    raw[0] = version
    if stamp is not None:
        struct.pack_into("<I", raw, 3, int(stamp.timestamp()))
    if not gps:
        struct.pack_into("<iiB", raw, 7, -2147483648, -2147483648, 0)
    return bytes(raw)


def test_v2_contract_and_optional_gps():
    for gps in (True, False):
        raw = packet(gps=gps)
        assert len(raw) == 45
        decoded = decode_binary_payload(raw)
        assert decoded["window_samples"] == 150
        assert (decoded["latitude"] is None) == (not gps)
    with pytest.raises(BinaryMeasurementError):
        decode_binary_payload(packet(version=1, gps=False))
    for offset, fmt, value in ((7, "i", 0), (11, "i", 0), (15, "B", 1)):
        raw = bytearray(packet(gps=False))
        struct.pack_into("<" + fmt, raw, offset, value)
        with pytest.raises(BinaryMeasurementError):
            decode_binary_payload(bytes(raw))


def test_v2_requires_activation_and_model(binary_case, binary_client, monkeypatch):
    case = binary_case
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", False)
    assert binary_client.post(URL, content=packet(), headers=headers(case)).status_code == 503
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", True)
    monkeypatch.setattr(ml_inference, "_profiles", {})
    assert binary_client.post(URL, content=packet(), headers=headers(case)).status_code == 503
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 0
    assert case.device.last_seen is None


def test_v2_without_gps_replay_and_latest(binary_case, binary_client, monkeypatch):
    case = binary_case
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", True)
    monkeypatch.setattr(ml_inference, "profile_ready", lambda _: True)
    assert binary_client.post(URL, content=packet(gps=False), headers=headers(case)).status_code == 201
    row = case.db.query(Telemetry).filter_by(animal_id=case.animal.id).one()
    assert row.latitude is row.longitude is row.location is None
    assert row.predicted_behavior == "Resting" and row.behavior_eligible is True
    monkeypatch.setattr(ml_inference, "profile_ready", lambda _: False)
    assert binary_client.post(URL, content=packet(gps=False), headers=headers(case)).status_code == 200
    latest = binary_client.get("/api/v1/telemetry/latest", params={"animal_id": case.animal.id}).json()[0]
    assert latest["latitude"] is None and latest["position_time"] is None
    assert binary_client.post("/api/v1/telemetry/", json={**json_equivalent(case), "latitude": None},
                              headers={"X-Device-Secret": case.secret}).status_code == 422


def test_lost_is_audit_only_and_recovers_explicitly(binary_case, binary_client, monkeypatch):
    case = binary_case
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", True)
    monkeypatch.setattr(ml_inference, "_profiles", {})
    start = utc_now() - timedelta(hours=1)
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={
        "status": "lost", "loss_started_at": start.isoformat()}).status_code == 200
    raw = packet(stamp=start + timedelta(minutes=1))
    assert binary_client.post(URL, content=raw, headers=headers(case)).status_code == 201
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).one().behavior_eligible is False
    case.prediction.assert_not_called()
    assert case.device.status == "lost"
    latest = binary_client.get("/api/v1/telemetry/latest", params={"animal_id": case.animal.id}).json()[0]
    assert latest["position_is_animal"] is False
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={"status": "active"}).status_code == 409
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={
        "status": "active", "confirm_remounted": True}).status_code == 200
    assert case.db.query(Telemetry).filter(Telemetry.animal_id == case.animal.id, eligible_clause()).count() == 0
    assert binary_client.post(URL, content=raw, headers=headers(case)).status_code == 200


@pytest.mark.parametrize("action", [{"ingestion_action": "revoke"}, {"status": "retired"}])
def test_revocation_blocks_both_transports_and_requires_new_secret(binary_case, binary_client, action):
    case = binary_case
    response = binary_client.patch("/api/v1/devices/BINARY-TEST", json=action)
    assert response.status_code == 200 and response.json()["ingestion_revoked_at"]
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 401
    assert binary_client.post("/api/v1/telemetry/", json=json_equivalent(case), headers={"X-Device-Secret": case.secret}).status_code == 401
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={"status": "active"}).status_code == 200
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 401
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={
        "ingestion_action": "restore", "device_secret": case.secret}).status_code == 409
    secret = generate_device_secret()
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={
        "ingestion_action": "restore", "device_secret": secret}).status_code == 200
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 401
    case.secret = secret
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 201


def test_retroactive_loss_invalidates_summary_and_preserves_raw_audit(binary_case, binary_client):
    case = binary_case
    stamp = (utc_now() - timedelta(hours=2)).replace(microsecond=0)
    raw = packet(version=1, stamp=stamp)
    assert binary_client.post(URL, content=raw, headers=headers(case)).status_code == 201
    day = stamp.astimezone(TARGET_TZ).date()
    assert aggregate_daily_behavior(case.db, case.animal.id, day).n_predictions == 1
    response = binary_client.patch("/api/v1/devices/BINARY-TEST", json={
        "status": "lost", "loss_started_at": (stamp - timedelta(minutes=1)).isoformat()})
    assert response.status_code == 200
    assert case.db.query(DailyBehaviorSummary).filter_by(animal_id=case.animal.id).count() == 0
    assert case.db.query(BehaviorRebuild).filter_by(animal_id=case.animal.id).count() == 1
    assert process_behavior_rebuilds(case.db) == 1
    assert case.db.query(BehaviorRebuild).filter_by(animal_id=case.animal.id).count() == 0
    row = case.db.query(Telemetry).filter_by(animal_id=case.animal.id).one()
    assert row.predicted_behavior == "Resting" and row.behavior_eligible is True
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={
        "status": "active", "confirm_remounted": True}).status_code == 200
    latest = binary_client.get("/api/v1/telemetry/latest", params={"animal_id": case.animal.id}).json()[0]
    assert latest["behavior_eligible"] is False and latest["latitude"] is None
    history = binary_client.get(f"/api/v1/telemetry/history/{case.animal.id}").json()
    assert history[0]["behavior_eligible"] is False
    case.db.flush()
    case.db.refresh(row)
    assert row.activity_state == "lying"  # Reading history never rewrites the source field.
    assert binary_client.post(URL, content=raw, headers=headers(case)).status_code == 200


def test_late_pre_loss_window_can_still_be_classified(binary_case, binary_client):
    case = binary_case
    start = utc_now() - timedelta(minutes=10)
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={
        "status": "lost", "loss_started_at": start.isoformat()}).status_code == 200
    assert binary_client.post(URL, content=packet(version=1, stamp=start - timedelta(seconds=30)),
                              headers=headers(case)).status_code == 201
    case.prediction.assert_called_once()
    assert case.device.status == "lost"


def test_window_overlapping_recovery_is_still_excluded(binary_case, binary_client):
    from app.services.telemetry_quality import measurement_eligible
    case = binary_case
    end = utc_now() - timedelta(minutes=1)
    case.db.add(DeviceLossPeriod(device_id=case.device.id, started_at=end - timedelta(hours=1),
                                 ended_at=end, declared_at=end, audit=[]))
    stamp = end + timedelta(seconds=2)
    case.db.add(Telemetry(animal_id=case.animal.id, device_id=case.device.id, time=stamp,
                          sample_rate=10, window_samples=150, behavior_eligible=True))
    case.db.commit()
    assert measurement_eligible(case.db, case.device, stamp, 10, 150) is False
    assert case.db.query(Telemetry).filter(Telemetry.animal_id == case.animal.id, eligible_clause()).count() == 0
    assert measurement_eligible(case.db, case.device, end + timedelta(seconds=15), 10, 150) is True


@pytest.mark.parametrize("body", [{"ingestion_action": "revoke"}, {"confirm_remounted": True},
                                 {"status": "lost"}, {"loss_started_at": "2026-09-01T00:00:00Z"}])
def test_quality_commands_require_manage_devices(binary_case, binary_client, body):
    case = binary_case
    case.user.role = "farmer"
    case.db.add(FarmMembership(user_id=case.user.id, farm_id=case.farm.id, role="vet", status="active"))
    case.db.commit()
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json=body).status_code == 403


def test_null_commands_and_future_loss_do_not_change_status(binary_case, binary_client):
    for body in ({"ingestion_action": None}, {"loss_started_at": None},
                 {"status": "lost", "loss_started_at": (utc_now() + timedelta(days=1)).isoformat()}):
        assert binary_client.patch("/api/v1/devices/BINARY-TEST", json=body).status_code == 422
    assert binary_case.device.status == "active"
    assert binary_case.db.query(DeviceLossPeriod).count() == 0


def test_json_metadata_profiles_are_explicit(binary_case, binary_client, monkeypatch):
    case = binary_case
    data = json_equivalent(case)
    data["window_samples"] = 150
    monkeypatch.setattr(ml_inference, "_profiles", {})
    assert binary_client.post("/api/v1/telemetry/", json=data,
                              headers={"X-Device-Secret": case.secret}).status_code == 503
    data.pop("sample_rate")
    assert binary_client.post("/api/v1/telemetry/", json=data,
                              headers={"X-Device-Secret": case.secret}).status_code == 201
    case.prediction.assert_not_called()


def test_last_known_position_keeps_its_original_time(binary_case, binary_client, monkeypatch):
    case = binary_case
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", True)
    monkeypatch.setattr(ml_inference, "profile_ready", lambda _: True)
    stamp = (utc_now() - timedelta(hours=1)).replace(microsecond=0)
    assert binary_client.post(URL, content=packet(stamp=stamp), headers=headers(case)).status_code == 201
    assert binary_client.post(URL, content=packet(stamp=stamp + timedelta(minutes=50), gps=False),
                              headers=headers(case)).status_code == 201
    data = binary_client.get("/api/v1/telemetry/latest", params={"animal_id": case.animal.id}).json()[0]
    from datetime import datetime
    assert datetime.fromisoformat(data["position_time"].replace("Z", "+00:00")) == stamp
    assert data["position_time"] != data["last_update"] and data["latitude"] == 34.6901


def test_replay_cannot_bypass_revocation(binary_case, binary_client):
    case = binary_case
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 201
    last_seen = case.device.last_seen
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={"ingestion_action": "revoke"}).status_code == 200
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 401
    assert case.device.last_seen == last_seen
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 1


def test_equivalent_json_and_v2_use_the_real_staged_model(binary_case, binary_client, monkeypatch):
    from pathlib import Path
    from test_binary_telemetry_api import REAL_PREDICT
    artifact = ml_inference._load_artifact(Path(__file__).resolve().parents[1] /
        "ml/models/behavior_classifier_v3_staged.pkl", (10, 150))
    assert artifact is not None
    monkeypatch.setattr(ml_inference, "_profiles", {(10, 150): artifact})
    monkeypatch.setattr(ml_inference, "predict_with_confidence", REAL_PREDICT)
    monkeypatch.setattr(settings, "BINARY_V2_ENABLED", True)
    case = binary_case
    raw = packet()
    data = decode_binary_payload(raw)
    data["timestamp"] = data["timestamp"].isoformat()
    first = binary_client.post("/api/v1/telemetry/", json={"device_id": case.device.id, **data},
                                headers={"X-Device-Secret": case.secret})
    assert first.status_code == 201
    case.db.query(Telemetry).filter_by(animal_id=case.animal.id).delete()
    case.db.commit()
    second = binary_client.post(URL, content=raw, headers=headers(case))
    assert second.status_code == 201
    for field in ("predicted_behavior", "behavior_confidence", "window_samples", "accel_x_mean", "latitude"):
        assert first.json()[field] == second.json()[field]
