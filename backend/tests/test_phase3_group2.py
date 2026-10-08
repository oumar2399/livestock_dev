"""Phase 3, group 2 (acceptance test 2026-10-07): add a device in the app (secret
returned once), device view with assigned animal / last position / health indicators.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import devices
from app.core.dependencies import get_current_user
from app.core.security import hash_device_secret, valid_device_secret
from app.db.database import get_db
from app.models.device import Device
from app.models.user import User
from app.services.device_health import describe_device, device_health
from test_b2_provenance_and_access import NOW, world  # noqa: F401  (fixture reuse)


@pytest.fixture
def api(world):  # noqa: F811
    app = FastAPI()
    app.include_router(devices.router, prefix="/api/v1")
    state = {"user": world.owner_b.id}
    app.dependency_overrides[get_db] = lambda: world.db
    app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, state["user"])

    def as_user(user):
        state["user"] = user.id
        return client

    with TestClient(app) as client:
        client.as_user = as_user
        yield client


def _new_id():
    return f"SIM-{uuid4().hex[:8]}".upper()


# ── 3.4 POST /devices ────────────────────────────────────────────────────────

@pytest.mark.parametrize("role", ["owner_b", "farmer_b"])
def test_owner_and_farmer_add_a_device_and_get_the_secret_once(world, api, role):  # noqa: F811
    device_id = _new_id()
    response = api.as_user(getattr(world, role)).post(
        "/api/v1/devices/", json={"device_id": device_id.lower(), "farm_id": world.farm_b.id})
    assert response.status_code == 201, response.text
    body = response.json()
    secret = body["device_secret"]
    assert body["id"] == device_id  # normalized to upper case
    assert valid_device_secret(secret)
    assert body["transport_id"] >= 100
    stored = world.db.get(Device, device_id)
    assert stored.device_secret == hash_device_secret(secret) != secret  # only the fingerprint
    assert stored.farm_id == world.farm_b.id and stored.status == "active"
    again = api.get(f"/api/v1/devices/{device_id}").json()
    assert "device_secret" not in again and secret not in str(again)
    listed = api.get("/api/v1/devices/", params={"farm_id": world.farm_b.id}).json()
    assert all("device_secret" not in item for item in listed)


def test_transport_id_is_the_lowest_free_one_from_100(world, api):  # noqa: F811
    taken = [Device(id=_new_id(), farm_id=world.farm_b.id, status="active", transport_id=t,
                    device_secret=hash_device_secret("a" * 64 if t == 100 else "b" * 64))
             for t in (100, 101)]
    world.db.add_all(taken)
    world.db.commit()
    first = api.post("/api/v1/devices/", json={"device_id": _new_id(), "farm_id": world.farm_b.id}).json()
    assert first["transport_id"] == 102


def test_vet_cannot_add_a_device(world, api):  # noqa: F811
    response = api.as_user(world.vet_b).post("/api/v1/devices/", json={"device_id": _new_id(), "farm_id": world.farm_b.id})
    assert response.status_code == 403


def test_device_id_must_be_new_and_well_formed(world, api):  # noqa: F811
    assert api.post("/api/v1/devices/", json={"device_id": world.device.id, "farm_id": world.farm_b.id}).status_code == 409
    for bad in ("ab", "M5 COLLAR", "collar/1", "x" * 51):
        assert api.post("/api/v1/devices/", json={"device_id": bad, "farm_id": world.farm_b.id}).status_code == 422, bad


def test_cannot_add_a_device_to_another_farm(world, api):  # noqa: F811
    response = api.as_user(world.owner_b).post("/api/v1/devices/", json={"device_id": _new_id(), "farm_id": world.farm_a.id})
    assert response.status_code == 403


# ── 3.4 / 3.7 device view ────────────────────────────────────────────────────

def test_device_view_shows_assigned_animal_and_health(world, api):  # noqa: F811
    body = api.get(f"/api/v1/devices/{world.device.id}").json()
    assert body["assigned_animal"] == {"id": world.animal.id, "name": world.animal.name}
    assert set(body["health"]) == {"offline", "offline_since", "last_fix_at", "needs_attention"}


def test_last_position_stays_inside_the_current_farms_periods(world):  # noqa: F811
    # The collar's newest fix belongs to farm B; seen from farm A it must not leak.
    in_b = describe_device(world.db, world.device)
    assert in_b["last_position"]["latitude"] == 2.0
    world.device.farm_id = world.farm_a.id
    in_a = describe_device(world.db, world.device)
    assert in_a["last_position"]["latitude"] == 1.0
    assert in_a["last_position"]["time"] < in_b["last_position"]["time"]
    world.device.farm_id = None
    assert describe_device(world.db, world.device)["last_position"] is None


def _device(**fields):
    base = {"last_seen": None, "battery_capacity": 80, "status": "active"}
    return SimpleNamespace(**{**base, **fields})


def _row(minutes_ago, battery=80):
    return SimpleNamespace(time=NOW - timedelta(minutes=minutes_ago), battery_level=battery)


@pytest.mark.parametrize("seen_minutes_ago,offline", [(None, True), (10, False), (30, False), (31, True)])
def test_offline_after_30_minutes_without_reception(seen_minutes_ago, offline):
    seen = None if seen_minutes_ago is None else (NOW - timedelta(minutes=seen_minutes_ago)).replace(tzinfo=None)
    health = device_health(_device(last_seen=seen), _row(1), _row(1), _row(1), NOW)
    assert health["offline"] is offline
    assert health["offline_since"] == (None if not offline or seen is None else seen.replace(tzinfo=timezone.utc))


@pytest.mark.parametrize("battery,low", [(25, True), (26, False), (0, True), (None, False)])
def test_low_battery_at_25_percent_or_less(battery, low):
    health = device_health(_device(last_seen=NOW, battery_capacity=battery), _row(1), _row(1), _row(1), NOW)
    assert ("low_battery" in health["needs_attention"]) is low


@pytest.mark.parametrize("fix_minutes_ago,flagged", [(None, True), (59, False), (61, True)])
def test_no_gps_fix_for_over_an_hour_while_sending(fix_minutes_ago, flagged):
    fix = None if fix_minutes_ago is None else _row(fix_minutes_ago)
    health = device_health(_device(last_seen=NOW), fix, _row(1), _row(1), NOW)
    assert ("no_gps_fix" in health["needs_attention"]) is flagged


@pytest.mark.parametrize("last_reading_ago,flagged", [(None, True), (59, False), (61, True)])
def test_battery_unreadable_for_over_an_hour(last_reading_ago, flagged):
    reading = None if last_reading_ago is None else _row(last_reading_ago)
    health = device_health(_device(last_seen=NOW), _row(1), _row(1, battery=None), reading, NOW)
    assert ("battery_unknown" in health["needs_attention"]) is flagged


def test_offline_or_retired_collars_get_no_sending_indicators():
    offline = device_health(_device(last_seen=NOW - timedelta(hours=2)), None, None, None, NOW)
    assert offline["offline"] and offline["needs_attention"] == []
    retired = device_health(_device(last_seen=NOW, status="retired", battery_capacity=0), None, None, None, NOW)
    assert retired["needs_attention"] == []


def test_indicators_never_change_the_status(world, api):  # noqa: F811
    world.device.last_seen = datetime(2020, 1, 1)
    world.db.commit()
    body = api.get(f"/api/v1/devices/{world.device.id}").json()
    assert body["health"]["offline"] is True and body["status"] == "active"
