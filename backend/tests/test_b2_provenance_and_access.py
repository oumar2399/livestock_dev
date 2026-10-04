"""B2 regression tests: provenance after a transfer, access rules, JSON ingestion, CSV safety.

All cases run on the disposable PostgreSQL database of the binary_* fixtures.
"""

import csv
import io
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.api.v1 import auth, farm_reports, history, notifications, reports, telemetry
from app.core.dependencies import get_current_user
from app.core.timezone import TARGET_TZ
from app.db.database import get_db
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.daily_summary import DailyBehaviorSummary
from app.models.device import Device
from app.models.farm import Farm
from app.models.membership import FarmMembership
from app.models.notification import NotificationDelivery
from app.models.provenance import AnimalTrackingPeriod
from app.models.telemetry import Telemetry
from app.models.user import User
from app.models.veterinary import VeterinaryCase, VeterinaryEntry
from app.services import notification_service
from app.services.csv_safety import neutralize_formula
from app.services.push_provider import MockPushProvider

NOW = datetime.now(timezone.utc).replace(microsecond=0)
TRANSFER = NOW - timedelta(hours=2)


def _naive(moment):
    return moment.astimezone(timezone.utc).replace(tzinfo=None)


def _user(db, label, role="farmer"):
    user = User(email=f"{label}-{uuid4().hex[:8]}@b2.test", password_hash="x", name=label, role=role)
    db.add(user)
    db.flush()
    return user


def _farm(db, owner, members=()):
    farm = Farm(owner_id=owner.id, name=f"B2 {uuid4().hex[:6]}")
    db.add(farm)
    db.flush()
    db.add(FarmMembership(user_id=owner.id, farm_id=farm.id, role="owner", status="active"))
    for user, role in members:
        db.add(FarmMembership(user_id=user.id, farm_id=farm.id, role=role, status="active"))
    db.flush()
    return farm


def _telemetry(db, animal, device, moment, latitude):
    db.add(Telemetry(time=moment, animal_id=animal.id, device_id=device.id, received_at=moment,
                     time_source="device_utc", protocol_version=2, behavior_eligible=True,
                     latitude=latitude, longitude=10.0, location=f"POINT(10.0 {latitude})",
                     satellites=8, activity=0.1, activity_state="lying", sample_rate=10,
                     window_samples=150, battery_level=50, predicted_behavior="Resting"))


def _summary(db, animal, day, pct):
    db.add(DailyBehaviorSummary(animal_id=animal.id, date=day, pct_active=pct, pct_resting=100 - pct,
                                n_predictions=10, avg_confidence=0.9, created_at=_naive(NOW)))


@pytest.fixture
def world(binary_db):
    """One animal moved from farm A to farm B two hours ago, with data on both sides."""
    db = binary_db
    owner_a, owner_b = _user(db, "ownerA"), _user(db, "ownerB")
    vet_b, farmer_b, admin = _user(db, "vetB"), _user(db, "farmerB"), _user(db, "admin", role="admin")
    farm_a = _farm(db, owner_a)
    farm_b = _farm(db, owner_b, [(vet_b, "vet"), (farmer_b, "farmer")])
    device = Device(id=f"B2-{uuid4().hex[:8]}", farm_id=farm_b.id, status="active")
    db.add(device)
    db.flush()
    animal = Animal(farm_id=farm_b.id, name="Transferred", status="active", assigned_device=device.id)
    db.add(animal)
    db.flush()
    db.add_all([
        AnimalTrackingPeriod(animal_id=animal.id, farm_id=farm_a.id, device_id=device.id,
                             valid_from=NOW - timedelta(days=10), valid_to=TRANSFER, source="registration"),
        AnimalTrackingPeriod(animal_id=animal.id, farm_id=farm_b.id, device_id=device.id,
                             valid_from=TRANSFER, source="farm_transfer"),
    ])
    _telemetry(db, animal, device, NOW - timedelta(days=3), 1.0)
    _telemetry(db, animal, device, NOW - timedelta(hours=5), 1.0)
    _telemetry(db, animal, device, NOW - timedelta(minutes=30), 2.0)

    old_day = (NOW - timedelta(days=5)).astimezone(TARGET_TZ).date()
    transfer_day = TRANSFER.astimezone(TARGET_TZ).date()
    _summary(db, animal, old_day, 10.0)
    _summary(db, animal, transfer_day, 20.0)

    alert_a = Alert(animal_id=animal.id, farm_id=farm_a.id, type="health", severity="warning",
                    title="A alert", triggered_at=_naive(NOW - timedelta(days=1)))
    legacy_a = Alert(animal_id=animal.id, farm_id=None, type="health", severity="info",
                     title="Legacy A alert", triggered_at=_naive(NOW - timedelta(days=3)))
    alert_b = Alert(animal_id=animal.id, farm_id=farm_b.id, type="health", severity="info",
                    title="B alert", triggered_at=_naive(NOW - timedelta(minutes=10)))
    db.add_all([alert_a, legacy_a, alert_b])
    case_a = VeterinaryCase(farm_id=farm_a.id, animal_id=animal.id, title="A case", status="provisional",
                            opened_by=owner_a.id)
    case_b = VeterinaryCase(farm_id=farm_b.id, animal_id=animal.id, title="B case", status="provisional",
                            opened_by=vet_b.id)
    db.add_all([case_a, case_b])
    db.flush()
    db.add_all([
        VeterinaryEntry(case_id=case_a.id, author_user_id=owner_a.id, entry_type="note",
                        content="A-farm clinical note", occurred_at=_naive(NOW - timedelta(days=2))),
        VeterinaryEntry(case_id=case_b.id, author_user_id=vet_b.id, entry_type="note",
                        content="B-farm clinical note", occurred_at=_naive(NOW - timedelta(minutes=20))),
    ])
    db.commit()
    return SimpleNamespace(db=db, farm_a=farm_a, farm_b=farm_b, animal=animal, device=device,
                           owner_a=owner_a, owner_b=owner_b, vet_b=vet_b, farmer_b=farmer_b, admin=admin,
                           alert_a=alert_a, legacy_a=legacy_a, alert_b=alert_b,
                           old_day=old_day, transfer_day=transfer_day)


@pytest.fixture
def client(world, monkeypatch):
    app = FastAPI()
    for module in (auth, farm_reports, history, notifications, reports, telemetry):
        app.include_router(module.router, prefix="/api/v1")
    state = {"user": world.owner_b.id}
    app.dependency_overrides[get_db] = lambda: world.db
    app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, state["user"])
    monkeypatch.setattr(notification_service, "ExpoPushProvider", MockPushProvider)

    def as_user(user):
        state["user"] = user.id
        return test_client

    with TestClient(app) as test_client:
        test_client.as_user = as_user
        yield test_client


def _csv(response):
    assert response.status_code == 200, response.text
    assert response.text.startswith("﻿")
    rows = list(csv.reader(io.StringIO(response.text.lstrip("﻿"))))
    return [dict(zip(rows[0], row)) for row in rows[1:]]


# ── 2.1 Provenance after a transfer ─────────────────────────────────────────

def test_new_farm_gets_no_old_farm_rows_on_history_latest_and_timeline(world, client):
    client.as_user(world.owner_b)
    rows = client.get(f"/api/v1/telemetry/history/{world.animal.id}", params={"hours": 168}).json()
    assert [row["latitude"] for row in rows] == [2.0]

    latest = client.get("/api/v1/telemetry/latest", params={"farm_id": world.farm_b.id}).json()
    assert [(row["animal_id"], row["latitude"]) for row in latest] == [(world.animal.id, 2.0)]

    items = client.get(f"/api/v1/animals/{world.animal.id}/timeline").json()["items"]
    alerts = {item["source_id"] for item in items if item["event_type"] == "alert"}
    assert alerts == {world.alert_b.id}
    assert [item for item in items if item["event_type"] == "daily_summary"] == []
    vet_notes = [item["data"]["content"] for item in items if item["event_type"] == "veterinary_entry"]
    assert vet_notes == ["B-farm clinical note"]


def test_transfer_day_summary_is_proven_for_neither_farm(world, client):
    client.as_user(world.admin)
    params = {"date_from": (world.old_day - timedelta(days=1)).isoformat(),
              "date_to": (world.transfer_day + timedelta(days=1)).isoformat()}
    rows = _csv(client.get("/api/v1/reports/export/daily_summaries", params=params))
    labels = {row["target_date"]: row["farm_id"] for row in rows}
    assert labels == {world.old_day.isoformat(): str(world.farm_a.id), world.transfer_day.isoformat(): ""}
    farm_b_rows = _csv(client.get("/api/v1/reports/export/daily_summaries",
                                  params={**params, "farm_id": world.farm_b.id}))
    assert farm_b_rows == []


def test_research_export_labels_rows_with_the_farm_at_measurement_time(world, client):
    client.as_user(world.admin)
    params = {"date_from": (NOW - timedelta(days=4)).astimezone(TARGET_TZ).date().isoformat(),
              "date_to": NOW.astimezone(TARGET_TZ).date().isoformat()}
    rows = _csv(client.get("/api/v1/reports/export/telemetry", params=params))
    assert sorted((row["latitude"], row["farm_id"]) for row in rows) == [
        ("1.0", str(world.farm_a.id)), ("1.0", str(world.farm_a.id)), ("2.0", str(world.farm_b.id))]
    farm_a_rows = _csv(client.get("/api/v1/reports/export/telemetry",
                                  params={**params, "farm_id": world.farm_a.id, "animal_id": world.animal.id}))
    assert [row["latitude"] for row in farm_a_rows] == ["1.0", "1.0"]
    alert_rows = _csv(client.get("/api/v1/reports/export/alerts", params=params))
    assert {row["alert_id"]: row["farm_id"] for row in alert_rows} == {
        str(world.alert_a.id): str(world.farm_a.id),
        str(world.legacy_a.id): str(world.farm_a.id),
        str(world.alert_b.id): str(world.farm_b.id),
    }


def test_telemetry_without_period_stays_in_admin_export_with_empty_farm(world, client):
    _telemetry(world.db, world.animal, world.device, NOW - timedelta(days=20), 3.0)
    world.db.commit()
    client.as_user(world.admin)
    day = (NOW - timedelta(days=20)).astimezone(TARGET_TZ).date().isoformat()
    rows = _csv(client.get("/api/v1/reports/export/telemetry", params={"date_from": day, "date_to": day}))
    assert [(row["latitude"], row["farm_id"], row["farm_name"]) for row in rows] == [("3.0", "", "")]
    filtered = _csv(client.get("/api/v1/reports/export/telemetry",
                               params={"date_from": day, "date_to": day, "farm_id": world.farm_b.id}))
    assert filtered == []
    client.as_user(world.owner_b)
    history_rows = client.get(f"/api/v1/telemetry/history/{world.animal.id}", params={"hours": 168}).json()
    assert 3.0 not in [row["latitude"] for row in history_rows]


# ── 2.2 Vet entries need view_veterinary ────────────────────────────────────

@pytest.mark.parametrize("event_types", [None, ["veterinary_entry"]])
def test_farmer_timeline_has_no_vet_entries(world, client, event_types):
    params = {"event_type": event_types} if event_types else {}
    farmer_items = client.as_user(world.farmer_b).get(
        f"/api/v1/animals/{world.animal.id}/timeline", params=params).json()["items"]
    assert [item for item in farmer_items if item["event_type"] == "veterinary_entry"] == []
    vet_items = client.as_user(world.vet_b).get(
        f"/api/v1/animals/{world.animal.id}/timeline", params=params).json()["items"]
    assert [item["data"]["content"] for item in vet_items if item["event_type"] == "veterinary_entry"] == [
        "B-farm clinical note"]


# ── 2.3 / 2.4 Dispatch and registration ─────────────────────────────────────

def test_dispatch_is_admin_only(world, client):
    assert client.as_user(world.owner_b).post("/api/v1/notifications/dispatch").status_code == 403
    owner_account = _user(world.db, "accountOwner", role="owner")
    world.db.commit()
    assert client.as_user(owner_account).post("/api/v1/notifications/dispatch").status_code == 403
    assert client.as_user(world.admin).post("/api/v1/notifications/dispatch").status_code == 200


@pytest.mark.parametrize("sent_role", ["owner", "vet", "admin", "not-a-role"])
def test_registration_ignores_the_role_field(world, client, sent_role):
    response = client.post("/api/v1/auth/register", json={
        "email": f"new-{uuid4().hex[:8]}@example.com", "password": "secret123", "name": "New", "role": sent_role})
    assert response.status_code == 201
    assert response.json()["user"]["role"] == "farmer"
    assert world.db.get(User, response.json()["user"]["id"]).role == "farmer"


# ── 2.5 Dispatcher uses memberships only ───────────────────────────────────

def test_revoked_owner_is_not_notified(world, client):
    db = world.db
    alert = Alert(animal_id=world.animal.id, farm_id=world.farm_b.id, type="geofence", severity="critical",
                  title="t", triggered_at=_naive(NOW))
    db.add(alert)
    db.flush()
    queued = notification_service.enqueue_alert_notification(db, alert)
    assert world.owner_b.id in {delivery.user_id for delivery in queued}
    db.query(FarmMembership).filter_by(user_id=world.owner_b.id, farm_id=world.farm_b.id).update({"status": "revoked"})
    db.commit()
    provider = MockPushProvider()
    notification_service.dispatch_pending_notifications(db, provider=provider)
    owner_delivery = db.query(NotificationDelivery).filter_by(alert_id=alert.id, user_id=world.owner_b.id).one()
    assert owner_delivery.status == "cancelled" and owner_delivery.last_error_code == "PERMISSION_REVOKED"
    second = Alert(animal_id=world.animal.id, farm_id=world.farm_b.id, type="geofence", severity="critical",
                   title="t2", triggered_at=_naive(NOW))
    db.add(second)
    db.flush()
    recipients = {delivery.user_id for delivery in notification_service.enqueue_alert_notification(db, second)}
    assert world.owner_b.id not in recipients  # farms.owner_id alone grants nothing


# ── 2.6 / 2.8 JSON ingestion ────────────────────────────────────────────────

def _json_packet(case, **changes):
    data = {"device_id": case.device.id, "latitude": 34.69, "longitude": 135.19, "activity": 0.1,
            "battery": 70, "sample_rate": 10, "window_samples": 150}
    data.update(changes)
    return data


def test_unprovisioned_json_is_rejected_and_no_device_created(binary_case, binary_client):
    case = binary_case
    unknown = f"UNKNOWN-{uuid4().hex[:6]}"
    response = binary_client.post("/api/v1/telemetry/", json=_json_packet(case, device_id=unknown),
                                  headers={"X-Device-Secret": case.secret})
    assert response.status_code == 401
    assert case.db.get(Device, unknown) is None
    assert binary_client.post("/api/v1/telemetry/", json=_json_packet(case)).status_code == 401
    case.device.transport_id = case.device.device_secret = None  # unprovisioned (pair constraint)
    case.db.commit()
    assert binary_client.post("/api/v1/telemetry/", json=_json_packet(case),
                              headers={"X-Device-Secret": case.secret}).status_code == 401
    assert case.db.query(Telemetry).count() == 0


def test_repeated_json_packet_follows_binary_replay_rules(binary_case, binary_client):
    case = binary_case
    stamp = (NOW - timedelta(minutes=5)).isoformat()
    auth_header = {"X-Device-Secret": case.secret}
    first = binary_client.post("/api/v1/telemetry/", json=_json_packet(case, timestamp=stamp), headers=auth_header)
    replay = binary_client.post("/api/v1/telemetry/", json=_json_packet(case, timestamp=stamp), headers=auth_header)
    conflict = binary_client.post("/api/v1/telemetry/", json=_json_packet(case, timestamp=stamp, battery=71),
                                  headers=auth_header)
    assert (first.status_code, replay.status_code, conflict.status_code) == (201, 200, 409)
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 1


def test_json_without_timestamp_uses_server_time_without_replay_detection(binary_case, binary_client):
    case = binary_case
    for _ in range(2):
        response = binary_client.post("/api/v1/telemetry/", json=_json_packet(case),
                                      headers={"X-Device-Secret": case.secret})
        assert response.status_code == 201
        assert response.json()["time_source"] == "server_reception"
    assert case.db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 2


def test_device_without_animal_gets_a_clear_message(binary_case, binary_client):
    case = binary_case
    case.animal.assigned_device = None
    case.db.commit()
    response = binary_client.post("/api/v1/telemetry/", json=_json_packet(case),
                                  headers={"X-Device-Secret": case.secret})
    assert response.status_code == 404
    detail = response.json()["detail"]
    assert "No active animal" in detail and str(case.farm.id) not in detail and "farm" not in detail.lower()


# ── 2.7 One CSV sanitizer ───────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (" =cmd", "' =cmd"), ("\t=cmd", "'\t=cmd"), ("=SUM(1)", "'=SUM(1)"), ("@x", "'@x"),
    ("+1+1", "'+1+1"), ("-2", "-2"), ("-12.5", "-12.5"), ("plain", "plain"),
])
def test_shared_sanitizer(value, expected):
    assert neutralize_formula(value) == expected


def test_farm_and_research_exports_neutralize_the_same_cells(world, client):
    db = world.db
    names = [" =cmd", "\t=cmd", "-2"]
    for name in names:
        device = Device(id=f"B2C-{uuid4().hex[:8]}", farm_id=world.farm_b.id, status="active")
        db.add(device)
        db.flush()
        animal = Animal(farm_id=world.farm_b.id, name=name, status="active", assigned_device=device.id)
        db.add(animal)
        db.flush()
        db.add(AnimalTrackingPeriod(animal_id=animal.id, farm_id=world.farm_b.id, device_id=device.id,
                                    valid_from=NOW - timedelta(days=3), source="registration"))
        db.add(Alert(animal_id=animal.id, farm_id=world.farm_b.id, type="health", severity="info",
                     title=name, triggered_at=_naive(NOW - timedelta(hours=1))))
    db.commit()
    expected = {"' =cmd", "'\t=cmd", "-2"}
    day_from = (NOW - timedelta(days=1)).astimezone(TARGET_TZ).date().isoformat()
    day_to = NOW.astimezone(TARGET_TZ).date().isoformat()

    research = _csv(client.as_user(world.admin).get("/api/v1/reports/export/alerts", params={
        "date_from": day_from, "date_to": day_to, "farm_id": world.farm_b.id}))
    assert expected <= {row["animal_name"] for row in research}

    farm = _csv(client.as_user(world.owner_b).get(
        f"/api/v1/farms/{world.farm_b.id}/reports/export/animal_quality",
        params={"date_from": day_from, "date_to": day_to}))
    assert expected <= {row["Animal Name"] for row in farm}
