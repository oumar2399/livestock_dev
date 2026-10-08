"""Phase 2 regression tests (acceptance test 2026-10-07).

A5: JSON telemetry refuses timestamps more than 300 s ahead, like the binary path;
the simulator never sends future packets.
A6: own farm-role change refused with a clear reason; access errors in English.
"""

import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import animals, farms, memberships
from app.core.dependencies import get_current_user
from app.core.timezone import utc_now
from app.db.database import get_db
from app.models.membership import FarmMembership
from app.models.telemetry import Telemetry
from app.models.user import User
from app.services.binary_telemetry import BinaryMeasurementError, validate_binary_timestamp
from test_b2_provenance_and_access import _json_packet, world  # noqa: F401  (fixture reuse)

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import simulate_telemetry  # noqa: E402

JSON_URL = "/api/v1/telemetry/"


# ── A5: future timestamps ───────────────────────────────────────────────────

def test_json_timestamp_too_far_ahead_is_refused_like_binary(binary_case, binary_client):
    case = binary_case
    ahead = utc_now() + timedelta(seconds=301)
    response = binary_client.post(JSON_URL, json=_json_packet(case, timestamp=ahead.isoformat()),
                                  headers={"X-Device-Secret": case.secret})
    assert response.status_code == 422
    with pytest.raises(BinaryMeasurementError) as binary_error:
        validate_binary_timestamp(ahead, utc_now())
    assert response.json()["detail"] == str(binary_error.value) == "Timestamp exceeds the allowed clock skew"
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 0


def test_json_timestamp_within_clock_skew_is_accepted(binary_case, binary_client):
    case = binary_case
    slightly_ahead = utc_now() + timedelta(seconds=60)
    response = binary_client.post(JSON_URL, json=_json_packet(case, timestamp=slightly_ahead.isoformat()),
                                  headers={"X-Device-Secret": case.secret})
    assert response.status_code == 201, response.text


def test_simulator_never_dates_a_packet_in_the_future():
    now = datetime(2026, 10, 8, 14, 37, 42)
    times = simulate_telemetry.packet_times(now)
    assert len(times) == 144
    assert times == sorted(times)
    assert times[-1] == datetime(2026, 10, 8, 14, 30) <= now
    assert all(b - a == timedelta(minutes=10) for a, b in zip(times, times[1:]))
    assert now - times[0] < timedelta(hours=24)


# ── A6: membership role changes and English errors ──────────────────────────

@pytest.fixture
def api(world, monkeypatch):  # noqa: F811
    app = FastAPI()
    for module in (animals, farms, memberships):
        app.include_router(module.router, prefix="/api/v1")
    state = {"user": world.owner_b.id}
    app.dependency_overrides[get_db] = lambda: world.db
    app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, state["user"])

    def as_user(user):
        state["user"] = user.id
        return client

    with TestClient(app) as client:
        client.as_user = as_user
        yield client


def _membership(db, user, farm):
    return db.query(FarmMembership).filter_by(user_id=user.id, farm_id=farm.id).one()


def test_member_cannot_change_own_role(world, api):  # noqa: F811
    own = _membership(world.db, world.owner_b, world.farm_b)
    response = api.as_user(world.owner_b).patch(
        f"/api/v1/farms/{world.farm_b.id}/members/{own.id}", json={"role": "farmer"})
    assert response.status_code == 403
    assert response.json()["detail"] == "You cannot change your own role."
    world.db.refresh(own)
    assert own.role == "owner"


def test_owner_still_changes_other_members_roles(world, api):  # noqa: F811
    vet = _membership(world.db, world.vet_b, world.farm_b)
    response = api.as_user(world.owner_b).patch(
        f"/api/v1/farms/{world.farm_b.id}/members/{vet.id}", json={"role": "farmer"})
    assert response.status_code == 200 and response.json()["role"] == "farmer"


def test_platform_admin_is_not_limited_by_the_own_role_rule(world, api):  # noqa: F811
    membership = FarmMembership(user_id=world.admin.id, farm_id=world.farm_b.id, role="vet", status="active")
    world.db.add(membership)
    world.db.commit()
    response = api.as_user(world.admin).patch(
        f"/api/v1/farms/{world.farm_b.id}/members/{membership.id}", json={"role": "farmer"})
    assert response.status_code == 200


def test_access_errors_are_in_english(world, api):  # noqa: F811
    client = api.as_user(world.farmer_b)
    assert client.get("/api/v1/farms/999999999").json()["detail"] == "Farm not found"
    assert client.get(f"/api/v1/farms/{world.farm_a.id}").json()["detail"] == "Access to this farm denied"
    response = client.post(f"/api/v1/farms/{world.farm_b.id}/members",
                           json={"user_email": "someone@example.com", "role": "vet"})
    assert response.status_code == 403
    assert response.json()["detail"] == "Permission denied: invite_members"
    assert client.get("/api/v1/animals/999999999").json()["detail"] == "Animal not found"
