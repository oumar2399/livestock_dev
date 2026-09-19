"""Real PostgreSQL equivalence, authentication, streaming and replay tests."""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest.mock import MagicMock

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import func
from sqlalchemy.orm import Session
from starlette.requests import Request
import pytest

from app.api.v1 import telemetry as telemetry_api
from app.core.security import generate_device_secret, hash_device_secret
from app.db.database import get_db
from app.models.animal import Animal
from app.models.device import Device
from app.models.farm import Farm
from app.models.telemetry import Telemetry
from app.models.user import User
from app.services import binary_telemetry, ml_inference
from test_binary_protocol import REFERENCE, changed


URL = "/api/v1/telemetry/binary"
REAL_PREDICT = ml_inference.predict_with_confidence


def headers(case, **changes):
    return {"Content-Type": "application/octet-stream", "X-Device-Secret": case.secret, **changes}


def json_equivalent(case):
    data = binary_telemetry.decode_binary_payload(REFERENCE)
    data["timestamp"] = data["timestamp"].isoformat()
    return {"device_id": case.device.id, **data}


def test_json_binary_have_identical_persisted_values(binary_case, binary_client):
    case = binary_case
    json_response = binary_client.post("/api/v1/telemetry/", json=json_equivalent(case), headers={"X-Device-Secret": case.secret})
    assert json_response.status_code == 201
    first = case.db.query(Telemetry).filter(Telemetry.animal_id == case.animal.id).one()
    provenance = {"location", "received_at", "protocol_version"}
    expected = {column.name: getattr(first, column.name) for column in Telemetry.__table__.columns if column.name not in provenance}
    case.db.delete(first)
    case.db.commit()
    binary_response = binary_client.post(URL, content=REFERENCE, headers=headers(case))
    assert binary_response.status_code == 201
    assert {k: v for k, v in binary_response.json().items() if k not in provenance} == {
        k: v for k, v in json_response.json().items() if k not in provenance}
    actual = case.db.query(Telemetry).filter(Telemetry.animal_id == case.animal.id).one()
    assert {name: getattr(actual, name) for name in expected} == expected
    point = case.db.query(func.ST_AsText(Telemetry.location)).filter(Telemetry.animal_id == case.animal.id).scalar()
    assert point == "POINT(135.1955 34.6901)"


@pytest.mark.parametrize("path", [URL, "/api/v1/telemetry/"])
@pytest.mark.parametrize("secret", [None, "invalid", "b" * 64])
def test_bad_credentials_have_no_effect(binary_case, binary_client, monkeypatch, path, secret):
    case = binary_case
    data = json_equivalent(case)
    decode = MagicMock()
    monkeypatch.setattr(binary_telemetry, "decode_binary_payload", decode)
    auth = {} if secret is None else {"X-Device-Secret": secret}
    if path == URL:
        response = binary_client.post(path, content=REFERENCE, headers={"Content-Type": "application/octet-stream", **auth})
    else:
        response = binary_client.post(path, json=data, headers=auth)
    assert response.status_code == 401 and response.json()["detail"] == "Invalid device credentials"
    decode.assert_not_called()
    case.prediction.assert_not_called()
    assert case.db.query(Telemetry).count() == 0
    assert case.device.last_seen is None and case.device.battery_capacity is None


def test_unknown_and_unprovisioned_have_same_error(binary_case, binary_client):
    case = binary_case
    unknown = binary_client.post(URL, content=changed(1, "H", 2), headers=headers(case))
    case.device.transport_id = case.device.device_secret = None
    case.db.commit()
    unprovisioned = binary_client.post(URL, content=REFERENCE, headers=headers(case))
    assert unknown.status_code == unprovisioned.status_code == 401
    assert unknown.json() == unprovisioned.json()
    legacy = json_equivalent(case)
    assert binary_client.post("/api/v1/telemetry/", json=legacy).status_code == 201


def test_rotation_closes_old_secret_on_both_transports(binary_case, binary_client):
    case = binary_case
    replacement = generate_device_secret()
    assert binary_client.patch("/api/v1/devices/BINARY-TEST", json={"device_secret": replacement}).status_code == 200
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 401
    assert binary_client.post("/api/v1/telemetry/", json=json_equivalent(case), headers={"X-Device-Secret": case.secret}).status_code == 401
    case.secret = replacement
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 201


@pytest.mark.parametrize("raw,expected", [(b"", 400), (REFERENCE[:44], 400), (REFERENCE + b"x", 413),
                                         (changed(0, "B", 3), 400), (changed(1, "H", 0), 400),
                                         (changed(15, "B", 0), 422), (changed(3, "I", 1), 422),
                                         (changed(3, "I", 4294967295), 422)])
def test_invalid_binary_packets(binary_case, binary_client, raw, expected):
    response = binary_client.post(URL, content=raw, headers=headers(binary_case))
    assert response.status_code == expected
    assert binary_case.db.query(Telemetry).count() == 0
    binary_case.prediction.assert_not_called()


def test_media_type_and_actual_length_are_checked(binary_case, binary_client):
    case = binary_case
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case, **{"Content-Type": "application/json"})).status_code == 415
    assert binary_client.post(URL, content=REFERENCE + b"x", headers=headers(case, **{"Content-Length": "45"})).status_code == 413
    assert binary_client.post(URL, content=iter([REFERENCE[:20], REFERENCE[20:]]), headers=headers(case)).status_code == 201


def test_stream_reader_stops_without_consuming_remaining_chunks():
    chunks = iter([b"a" * 30, b"b" * 20, b"c" * 100000])
    reads = []

    async def receive():
        chunk = next(chunks)
        reads.append(len(chunk))
        return {"type": "http.request", "body": chunk, "more_body": True}

    request = Request({"type": "http", "headers": [(b"content-type", b"application/octet-stream")]}, receive)
    with pytest.raises(HTTPException) as exc:
        asyncio.run(telemetry_api.read_binary_body(request))
    assert exc.value.status_code == 413 and reads == [30, 20]


def test_replay_reuses_row_and_does_not_rewind_battery(binary_case, binary_client):
    case = binary_case
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 201
    case.device.battery_capacity = 60
    case.db.commit()
    case.prediction.reset_mock()
    response = binary_client.post(URL, content=REFERENCE, headers=headers(case))
    assert response.status_code == 200
    assert case.db.query(Telemetry).count() == 1 and case.device.battery_capacity == 60
    case.prediction.assert_not_called()
    conflict = binary_client.post(URL, content=changed(17, "h", 21), headers=headers(case))
    assert conflict.status_code == 409
    assert float(case.db.query(Telemetry).one().accel_x_mean) == 0.02


def test_model_profile_mismatch_and_unavailable_model(binary_case, binary_client, monkeypatch):
    case = binary_case
    monkeypatch.setattr(ml_inference, "get_model_info", lambda: {"target_freq": 10, "window_samples": 150})
    assert binary_client.post(URL, content=REFERENCE, headers=headers(case)).status_code == 409
    assert case.db.query(Telemetry).count() == 0
    monkeypatch.setattr(ml_inference, "get_model_info", lambda: None)
    case.prediction.return_value = (None, None)
    result = binary_client.post(URL, content=REFERENCE, headers=headers(case))
    assert result.status_code == 201 and result.json()["predicted_behavior"] is None


def test_equivalence_with_real_active_model(binary_case, binary_client, monkeypatch):
    ml_inference.load_model()
    assert ml_inference.get_model_info()["window_samples"] == 50
    monkeypatch.setattr(ml_inference, "predict_with_confidence", REAL_PREDICT)
    test_json_binary_have_identical_persisted_values(binary_case, binary_client)


def test_concurrent_identical_packets_create_only_one_row(binary_engine, monkeypatch):
    monkeypatch.setattr(ml_inference, "predict_with_confidence", lambda _: ("Resting", 0.9))
    monkeypatch.setattr(ml_inference, "get_model_info", lambda: None)
    secret = generate_device_secret()
    with Session(binary_engine) as db:
        user = User(email="concurrency@example.com", password_hash="test-only", name="Concurrency", role="admin")
        db.add(user)
        db.flush()
        farm = Farm(name="Concurrency", owner_id=user.id)
        db.add(farm)
        db.flush()
        device = Device(id="CONCURRENT", farm_id=farm.id, transport_id=40000, device_secret=hash_device_secret(secret))
        animal = Animal(farm_id=farm.id, name="Concurrency", assigned_device=device.id, status="active")
        db.add_all([device, animal])
        db.commit()
        animal_id = animal.id
    app = FastAPI()
    app.include_router(telemetry_api.router, prefix="/api/v1")

    def session():
        with Session(binary_engine) as db:
            yield db

    app.dependency_overrides[get_db] = session
    barrier = Barrier(2)

    def send():
        with TestClient(app) as client:
            barrier.wait(timeout=10)
            return client.post(URL, content=changed(1, "H", 40000), headers={
                "Content-Type": "application/octet-stream", "X-Device-Secret": secret,
            }).status_code

    with ThreadPoolExecutor(max_workers=2) as workers:
        futures = [workers.submit(send) for _ in range(2)]
        assert sorted(future.result(timeout=20) for future in futures) == [200, 201]
    with Session(binary_engine) as db:
        assert db.query(Telemetry).filter(Telemetry.animal_id == animal_id).count() == 1
