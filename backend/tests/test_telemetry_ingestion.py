"""HTTP characterization of the JSON ingestion contract (provisioned devices only)."""

from datetime import datetime, timezone
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import IntegrityError

from app.api.v1 import telemetry as telemetry_api
from app.core.security import generate_device_secret, hash_device_secret
from app.db.database import get_db
from app.models.animal import Animal
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.services import ml_inference
from app.services import telemetry_ingestion
from app.schemas.telemetry import TelemetryCreate


SECRET = generate_device_secret()


@pytest.fixture
def ingestion_client(monkeypatch):
    state = SimpleNamespace(
        animal=Animal(id=7, farm_id=3, name="Test", status="active"),
        device=Device(id="M5-test", farm_id=3, status="active", device_secret=hash_device_secret(SECRET)),
        saved=[],
    )
    db = MagicMock()

    def query(model):
        result = MagicMock()
        result.filter.return_value = result
        result.with_for_update.return_value = result
        result.populate_existing.return_value = result
        result.all.return_value = []
        result.first.side_effect = lambda: (
            state.animal if model is Animal else None if model is Telemetry else state.device
        )
        return result

    db.query.side_effect = query
    db.add.side_effect = state.saved.append
    prediction = MagicMock(return_value=(None, None))
    monkeypatch.setattr(ml_inference, "predict_with_confidence", prediction)
    monkeypatch.setattr(ml_inference, "profile_ready", lambda profile: profile == (10, 150))
    app = FastAPI()
    app.include_router(telemetry_api.router, prefix="/api/v1")
    app.dependency_overrides[get_db] = lambda: db
    with TestClient(app, headers={"X-Device-Secret": SECRET}) as client:
        yield client, state, db, prediction


def payload(**changes):
    return dict(dict(device_id="M5-test", latitude=34.6901, longitude=135.1955,
                     activity=0.12, battery=78, sample_rate=10, window_samples=150), **changes)


def inserted(state):
    return next(row for row in state.saved if isinstance(row, Telemetry))


def test_minimal_json_preserves_response_and_server_time(ingestion_client):
    client, state, db, _ = ingestion_client
    before = datetime.now(timezone.utc)
    response = client.post("/api/v1/telemetry/", json=payload())
    after = datetime.now(timezone.utc)
    assert response.status_code == 201
    body = response.json()
    assert body["battery"] == 78 and "battery_level" not in body
    assert body["animal_id"] == 7 and body["activity_state"] == "lying"
    row = inserted(state)
    assert before <= row.time <= after
    assert row.location == "POINT(135.1955 34.6901)"
    assert row.predicted_behavior is None and row.sample_rate == 10
    assert state.device.battery_capacity == 78
    db.commit.assert_called_once()


@pytest.mark.parametrize("stamp", ["2026-09-01T15:00:00Z", "2026-09-02T00:00:00+09:00", "2026-09-01T15:00:00"])
def test_explicit_timestamps_are_normalized_to_utc(ingestion_client, stamp):
    client, state, _, _ = ingestion_client
    assert client.post("/api/v1/telemetry/", json=payload(timestamp=stamp)).status_code == 201
    assert inserted(state).time == datetime(2026, 9, 1, 15, tzinfo=timezone.utc)


@pytest.mark.parametrize("activity,expected", [(0, "lying"), (0.149, "lying"), (0.15, "standing"), (0.5, "walking"), (1, "running")])
def test_activity_thresholds(ingestion_client, activity, expected):
    client, _, _, _ = ingestion_client
    data = payload()
    data["activity"] = activity
    response = client.post("/api/v1/telemetry/", json=data)
    assert response.status_code == 201
    assert response.json()["activity_state"] == expected


def test_complete_json_preserves_source_fields_and_separates_ml(ingestion_client):
    client, state, _, prediction = ingestion_client
    prediction.return_value = ("Active", 0.82)
    data = payload(activity_state="standing", activity_std=0.02, sample_rate=10,
                   window_samples=150, altitude=12.3, speed=0, satellites=8,
                   temperature=38, signal_strength=-70,
                   predicted_behavior="client-value", behavior_confidence=1)
    for axis in "xyz":
        data.update({f"accel_{axis}_mean": 0.01, f"accel_{axis}_std": 0.02,
                     f"accel_{axis}_min": -0.01, f"accel_{axis}_max": 0.05})
    response = client.post("/api/v1/telemetry/", json=data)
    assert response.status_code == 201
    row = inserted(state)
    for name in ("altitude", "speed", "satellites", "activity_std", "sample_rate", "window_samples", "temperature", "signal_strength"):
        assert getattr(row, name) == data[name]
    assert row.activity_state == "standing"
    assert row.predicted_behavior == "Active" and row.behavior_confidence == 0.82
    assert row.accel_z_max == 0.05
    prediction.assert_called_once()


@pytest.mark.parametrize("error", [ValueError("bad feature"), TypeError("bad type"), RuntimeError("unavailable")])
def test_prediction_errors_do_not_discard_telemetry(ingestion_client, error):
    client, state, _, prediction = ingestion_client
    prediction.side_effect = error
    assert client.post("/api/v1/telemetry/", json=payload()).status_code == 201
    assert inserted(state).predicted_behavior is None


def test_unknown_device_is_rejected_and_never_created(ingestion_client):
    client, state, db, prediction = ingestion_client
    state.animal = state.device = None
    response = client.post("/api/v1/telemetry/", json=payload())
    assert response.status_code == 401
    assert state.saved == []
    db.commit.assert_not_called()
    prediction.assert_not_called()


@pytest.mark.parametrize("stored,sent", [(None, SECRET), ("provisioned", None), ("provisioned", "0" * 64)])
def test_unprovisioned_device_or_bad_secret_is_rejected(ingestion_client, stored, sent):
    client, state, db, _ = ingestion_client
    if stored is None:
        state.device.device_secret = None
    headers = {} if sent is None else {"X-Device-Secret": sent}
    client.headers.pop("X-Device-Secret", None)
    assert client.post("/api/v1/telemetry/", json=payload(), headers=headers).status_code == 401
    assert state.saved == []
    db.commit.assert_not_called()


def test_device_without_active_animal_gets_a_clear_404(ingestion_client):
    client, state, db, prediction = ingestion_client
    state.animal = None
    response = client.post("/api/v1/telemetry/", json=payload())
    assert response.status_code == 404
    assert "farm" not in response.json()["detail"].lower()
    assert state.saved == []
    db.commit.assert_not_called()
    prediction.assert_not_called()


def test_cross_farm_device_is_rejected_without_exposing_farm_ids(ingestion_client):
    client, state, db, prediction = ingestion_client
    state.device.farm_id = 4
    response = client.post("/api/v1/telemetry/", json=payload())
    assert response.status_code == 409
    assert not any(char.isdigit() for char in response.json()["detail"])
    db.commit.assert_not_called()
    prediction.assert_not_called()


def test_server_stamped_collision_is_409_not_500(ingestion_client):
    client, _, db, _ = ingestion_client
    original = Exception("database conflict")
    original.pgcode = "23505"
    original.diag = SimpleNamespace(constraint_name="telemetry_pkey")
    db.flush.side_effect = IntegrityError("INSERT", {}, original)
    assert client.post("/api/v1/telemetry/", json=payload()).status_code == 409


@pytest.mark.parametrize("status", ["lost", "retired"])
def test_telemetry_never_reactivates_a_lost_or_retired_device(ingestion_client, status):
    client, state, _, _ = ingestion_client
    state.device.status = status
    assert client.post("/api/v1/telemetry/", json=payload()).status_code == (201 if status == "lost" else 401)
    assert state.device.status == status


def test_invalid_json_does_not_access_database(ingestion_client):
    client, _, db, _ = ingestion_client
    data = payload()
    data["latitude"] = 91
    assert client.post("/api/v1/telemetry/", json=data).status_code == 422
    db.query.assert_not_called()


@pytest.mark.parametrize("constraint,code,reuse", [
    ("telemetry_pkey", "23505", True),
    ("7_32_telemetry_pkey", "23505", True),
    ("another_unique_key", "23505", False),
    ("telemetry_pkey", "23503", False),
])
def test_only_targeted_primary_key_conflicts_are_reused(ingestion_client, monkeypatch, constraint, code, reuse):
    _, _, db, _ = ingestion_client
    data = TelemetryCreate(**payload(timestamp=datetime(2026, 9, 1, tzinfo=timezone.utc)))
    row = Telemetry(**data.model_dump(exclude={"timestamp", "battery"}),
                    time=data.timestamp, animal_id=7, battery_level=data.battery)
    row.activity_state = "lying"
    row.activity = Decimal("0.120")
    lookup = MagicMock(side_effect=[None, row])
    monkeypatch.setattr(telemetry_ingestion, "_existing_measurement", lookup)
    original = Exception("database conflict")
    original.pgcode = code
    original.diag = SimpleNamespace(constraint_name=constraint)
    db.commit.side_effect = IntegrityError("INSERT", {}, original)
    if reuse:
        result = telemetry_ingestion.ingest_telemetry(data, db, idempotent=True)
        assert result.telemetry is row and result.created is False
        assert lookup.call_count == 2
    else:
        with pytest.raises(IntegrityError):
            telemetry_ingestion.ingest_telemetry(data, db, idempotent=True)
        assert lookup.call_count == 1
    db.rollback.assert_called_once()


def test_replay_comparison_normalizes_sql_precision():
    data = TelemetryCreate(**payload(activity_std=0.01234))
    row = Telemetry(**data.model_dump(exclude={"battery", "timestamp"}), battery_level=data.battery)
    row.activity = Decimal("0.120")
    row.activity_std = Decimal("0.012")
    row.activity_state = "lying"
    assert telemetry_ingestion._reuse_measurement(row, data).created is False
    row.activity_std = Decimal("0.013")
    with pytest.raises(HTTPException) as exc:
        telemetry_ingestion._reuse_measurement(row, data)
    assert exc.value.status_code == 409
