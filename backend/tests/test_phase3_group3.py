"""Phase 3, group 3 (acceptance test 2026-10-07): admin transfer of an animal in the
app, and the visibility rule after a transfer — the health history follows the animal,
location data and farm-bound alerts do not.
"""

from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import alerts, animals, history, telemetry, veterinary
from app.core.dependencies import get_current_user
from app.db.database import get_db
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.daily_summary import DailyBehaviorSummary
from app.models.device import Device
from app.models.provenance import AnimalTrackingPeriod
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.veterinary import VeterinaryCase, VeterinaryEntry
from test_b2_provenance_and_access import _farm, _user

NOW = datetime.now(timezone.utc).replace(microsecond=0)


def _naive(moment):
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


@pytest.fixture
def herd(binary_db):
    """An animal tracked in farm A for 10 days, with farm A data of every kind."""
    db = binary_db
    owner_a, owner_b, farmer_b, admin = (_user(db, "ownerA"), _user(db, "ownerB"), _user(db, "farmerB"),
                                         _user(db, "admin", role="admin"))
    vet_a = _user(db, "vetA")
    farm_a = _farm(db, owner_a, [(vet_a, "vet")])
    farm_b = _farm(db, owner_b, [(farmer_b, "farmer")])
    device = Device(id=f"P3-{uuid4().hex[:8]}".upper(), farm_id=farm_a.id, status="active")
    db.add(device)
    db.flush()
    animal = Animal(farm_id=farm_a.id, name="Bella", status="active", assigned_device=device.id)
    db.add(animal)
    db.flush()
    db.add(AnimalTrackingPeriod(animal_id=animal.id, farm_id=farm_a.id, device_id=device.id,
                                valid_from=NOW - timedelta(days=10), source="registration"))
    db.add(Telemetry(time=NOW - timedelta(hours=3), animal_id=animal.id, device_id=device.id, received_at=NOW,
                     latitude=5.0, longitude=10.0, location="POINT(10.0 5.0)", satellites=8, activity=0.1,
                     sample_rate=10, window_samples=150, behavior_eligible=True))
    health = Alert(animal_id=animal.id, farm_id=farm_a.id, type="activity_deviation_low", severity="warning",
                   title="Low activity in A", triggered_at=_naive(NOW - timedelta(days=1)))
    geofence = Alert(animal_id=animal.id, farm_id=farm_a.id, type="geofence", severity="critical",
                     title="Danger zone in A", triggered_at=_naive(NOW - timedelta(hours=5)))
    db.add_all([health, geofence])
    db.add(DailyBehaviorSummary(animal_id=animal.id, date=(NOW - timedelta(days=2)).date(), pct_active=30,
                                pct_resting=70, n_predictions=10, avg_confidence=0.9, created_at=_naive(NOW)))
    case = VeterinaryCase(farm_id=farm_a.id, animal_id=animal.id, title="Lameness (A)", status="provisional",
                          opened_by=vet_a.id)
    db.add(case)
    db.flush()
    db.add(VeterinaryEntry(case_id=case.id, author_user_id=vet_a.id, entry_type="intervention",
                           content="Bandage, re-check in 3 days", occurred_at=_naive(NOW - timedelta(days=1))))
    db.commit()
    return SimpleNamespace(db=db, farm_a=farm_a, farm_b=farm_b, owner_a=owner_a, owner_b=owner_b,
                           farmer_b=farmer_b, vet_a=vet_a, admin=admin, device=device, animal=animal,
                           health=health, geofence=geofence, case=case)


@pytest.fixture
def api(herd):
    app = FastAPI()
    for module in (alerts, animals, history, telemetry, veterinary):
        app.include_router(module.router, prefix="/api/v1")
    state = {"user": herd.admin.id}
    app.dependency_overrides[get_db] = lambda: herd.db
    app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, state["user"])

    def as_user(user):
        state["user"] = user.id
        return client

    with TestClient(app) as client:
        client.as_user = as_user
        yield client


def _transfer(api, herd):
    return api.as_user(herd.admin).post(f"/api/v1/animals/{herd.animal.id}/transfer",
                                        json={"target_farm_id": herd.farm_b.id})


# ── The transfer itself ─────────────────────────────────────────────────────

def test_only_the_admin_transfers(herd, api):
    for user in (herd.owner_a, herd.owner_b):
        assert api.as_user(user).post(f"/api/v1/animals/{herd.animal.id}/transfer",
                                      json={"target_farm_id": herd.farm_b.id}).status_code == 403
    assert herd.db.get(Animal, herd.animal.id).farm_id == herd.farm_a.id


def test_transfer_rejects_unknown_or_same_farm(herd, api):
    client = api.as_user(herd.admin)
    url = f"/api/v1/animals/{herd.animal.id}/transfer"
    assert client.post(url, json={"target_farm_id": 999999999}).status_code == 404
    assert client.post(url, json={"target_farm_id": herd.farm_a.id}).status_code == 409
    assert client.post("/api/v1/animals/999999999/transfer", json={"target_farm_id": herd.farm_b.id}).status_code == 404


def test_transfer_moves_animal_and_collar_and_keeps_tracking_periods_right(herd, api):
    response = _transfer(api, herd)
    assert response.status_code == 200, response.text
    db = herd.db
    db.expire_all()
    assert db.get(Animal, herd.animal.id).farm_id == herd.farm_b.id
    assert db.get(Device, herd.device.id).farm_id == herd.farm_b.id  # the collar stays on the animal
    periods = db.query(AnimalTrackingPeriod).filter_by(animal_id=herd.animal.id) \
        .order_by(AnimalTrackingPeriod.valid_from).all()
    assert [(p.farm_id, p.source) for p in periods] == [(herd.farm_a.id, "registration"), (herd.farm_b.id, "farm_transfer")]
    assert periods[0].valid_to == periods[1].valid_from and periods[1].valid_to is None
    assert periods[1].device_id == herd.device.id


def test_old_farms_open_alerts_are_resolved_as_animal_transferred(herd, api):
    _transfer(api, herd)
    for alert_id in (herd.health.id, herd.geofence.id):
        alert = herd.db.get(Alert, alert_id)
        herd.db.refresh(alert)
        assert alert.resolved_at is not None
        assert alert.alert_metadata["resolved_reason"] == "animal_transferred"
        assert alert.alert_metadata["transferred_to_farm_id"] == herd.farm_b.id


# ── What each farm sees afterwards ──────────────────────────────────────────

def test_receiving_farm_sees_health_history_not_locations_or_geofence_alerts(herd, api):
    _transfer(api, herd)
    client = api.as_user(herd.owner_b)
    listed = {a["id"] for a in client.get("/api/v1/alerts/", params={"farm_id": herd.farm_b.id}).json()["alerts"]}
    assert herd.health.id in listed and herd.geofence.id not in listed

    items = client.get(f"/api/v1/animals/{herd.animal.id}/timeline").json()["items"]
    kinds = {(item["event_type"], item["source_id"]) for item in items}
    assert ("alert", herd.health.id) in kinds and ("alert", herd.geofence.id) not in kinds
    assert any(item["event_type"] == "daily_summary" for item in items)
    assert [i["data"]["content"] for i in items if i["event_type"] == "veterinary_entry"] == ["Bandage, re-check in 3 days"]

    assert client.get(f"/api/v1/telemetry/history/{herd.animal.id}", params={"hours": 168}).json() == []


def test_previous_farms_cases_are_read_only_for_the_receiving_farm(herd, api):
    _transfer(api, herd)
    client = api.as_user(herd.farmer_b)
    cases = client.get(f"/api/v1/farms/{herd.farm_b.id}/veterinary-cases").json()["cases"]
    assert [c["id"] for c in cases] == [herd.case.id]
    detail = client.get(f"/api/v1/farms/{herd.farm_b.id}/veterinary-cases/{herd.case.id}")
    assert detail.status_code == 200 and detail.json()["farm_id"] == herd.farm_a.id
    entry = client.post(f"/api/v1/farms/{herd.farm_b.id}/veterinary-cases/{herd.case.id}/entries",
                        json={"entry_type": "observation", "content": "Walks better"})
    assert entry.status_code == 403
    assert "read-only" in entry.json()["detail"]


def test_previous_farm_keeps_its_own_alerts_and_no_longer_sees_the_animal(herd, api):
    _transfer(api, herd)
    client = api.as_user(herd.owner_a)
    listed = {a["id"] for a in client.get("/api/v1/alerts/", params={"farm_id": herd.farm_a.id}).json()["alerts"]}
    assert {herd.health.id, herd.geofence.id} <= listed
    assert client.get(f"/api/v1/animals/{herd.animal.id}").status_code == 403
    later = Alert(animal_id=herd.animal.id, farm_id=herd.farm_b.id, type="activity_deviation_high",
                  severity="warning", title="High activity in B", triggered_at=_naive(NOW))
    herd.db.add(later)
    herd.db.commit()
    listed = {a["id"] for a in client.get("/api/v1/alerts/", params={"farm_id": herd.farm_a.id}).json()["alerts"]}
    assert later.id not in listed


def test_alert_handling_follows_the_same_visibility(herd, api):
    _transfer(api, herd)
    for alert in (herd.health, herd.geofence):  # reopen both to test acknowledgement
        alert.resolved_at = None
    herd.db.commit()
    client = api.as_user(herd.farmer_b)
    stamp = {"acknowledged_at": NOW.isoformat()}
    assert client.patch(f"/api/v1/alerts/{herd.health.id}", json=stamp).status_code == 200
    assert client.patch(f"/api/v1/alerts/{herd.geofence.id}", json=stamp).status_code == 403
