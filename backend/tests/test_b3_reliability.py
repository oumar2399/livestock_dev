"""B3 regression tests: notification intents, location quality, delete guard,
vet status journal, daily job lock, push credentials, danger alert lifecycle.

Database cases run on disposable PostgreSQL databases (binary_* fixtures, or the
isolated default engine for the daily job, which opens its own sessions).
"""

import io
import json
from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import text

from app.api.v1 import admin, animals
from app.core.dependencies import get_current_user, require_admin
from app.db.database import SessionLocal, engine, get_db
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.device import Device
from app.models.geofence import Geofence
from app.models.job_run import DailyJobRun
from app.models.membership import FarmMembership
from app.models.notification import NotificationDelivery, PushDevice
from app.models.provenance import AnimalTrackingPeriod
from app.models.telemetry import Telemetry
from app.models.telemetry_quality import DeviceLossPeriod
from app.models.user import User
from app.models.veterinary import VeterinaryEntry
from app.schemas.veterinary import VeterinaryCaseCreate, VeterinaryCaseUpdate
from app.services import geofence_engine, job_tracking, notification_service, push_provider
from app.services.location_service import get_location_history
from app.services.push_provider import ExpoPushProvider, MockPushProvider
from app.services.veterinary_service import create_veterinary_case, update_veterinary_case

UTC = timezone.utc
PASTURE = "SRID=4326;POLYGON((10.000 5.000,10.010 5.000,10.010 5.010,10.000 5.010,10.000 5.000))"
DANGER = "SRID=4326;POLYGON((10.020 5.000,10.025 5.000,10.025 5.005,10.020 5.005,10.020 5.000))"
IN_PASTURE, IN_DANGER, OUTSIDE = (5.005, 10.005), (5.002, 10.022), (5.005, 10.015)


def _member(db, farm, role="farmer"):
    user = User(email=f"b3-{uuid4().hex[:8]}@example.com", password_hash="x", name="B3", role="farmer")
    db.add(user)
    db.flush()
    db.add(FarmMembership(user_id=user.id, farm_id=farm.id, role=role, status="active"))
    db.flush()
    return user


def _zones(db, farm):
    db.add_all([Geofence(farm_id=farm.id, name="pasture", type="pasture", polygon=PASTURE, active=True),
                Geofence(farm_id=farm.id, name="danger", type="danger", polygon=DANGER, active=True)])
    db.flush()


def _json_fix(client, case, when, position):
    return client.post("/api/v1/telemetry/", headers={"X-Device-Secret": case.secret}, json={
        "device_id": case.device.id, "timestamp": when.isoformat(), "latitude": position[0],
        "longitude": position[1], "satellites": 8, "activity": 0.1, "battery": 70,
        "sample_rate": 10, "window_samples": 150})


def _deliveries(db, alert_id):
    return db.query(NotificationDelivery).filter_by(alert_id=alert_id).count()


# ── 3.1 Notification intent in the alert's transaction ─────────────────────

def test_intent_failure_keeps_telemetry_and_alert_then_dispatch_reconciles(binary_case, binary_client, monkeypatch):
    case = binary_case
    db = case.db
    _zones(db, case.farm)
    _member(db, case.farm)
    db.commit()

    def failing_enqueue(session, alert):
        session.execute(text("SELECT 1/0"))  # real SQL error inside the savepoint
    original = notification_service.enqueue_alert_notification
    monkeypatch.setattr(notification_service, "enqueue_alert_notification", failing_enqueue)
    response = _json_fix(binary_client, case, datetime.now(UTC) - timedelta(seconds=10), IN_DANGER)
    assert response.status_code == 201
    alert = db.query(Alert).filter_by(animal_id=case.animal.id, severity="critical").one()
    assert db.query(Telemetry).filter_by(animal_id=case.animal.id).count() == 1
    assert _deliveries(db, alert.id) == 0

    monkeypatch.setattr(notification_service, "enqueue_alert_notification", original)
    notification_service.dispatch_pending_notifications(db, provider=MockPushProvider())
    assert _deliveries(db, alert.id) == 1


def test_reconciliation_scope(binary_case):
    db = binary_case.db
    _member(db, binary_case.farm)
    now = datetime.utcnow()

    def alert(**changes):
        row = Alert(animal_id=binary_case.animal.id, farm_id=binary_case.farm.id, type="activity_deviation_high",
                    severity="warning", title="t", triggered_at=now - timedelta(hours=1))
        for name, value in changes.items():
            setattr(row, name, value)
        db.add(row)
        db.flush()
        return row
    recent = alert()
    old = alert(triggered_at=now - notification_service.MISSING_INTENT_WINDOW - timedelta(minutes=1))
    resolved = alert(resolved_at=now)
    invalidated = alert(alert_metadata={"quality_invalidated_at": now.isoformat()})
    suppressed = alert(alert_metadata={notification_service.NOTIFICATION_SUPPRESSED: "covered_by_danger_alert"})
    db.commit()
    notification_service.reconcile_missing_intents(db)
    assert _deliveries(db, recent.id) == 1
    for skipped in (old, resolved, invalidated, suppressed):
        assert _deliveries(db, skipped.id) == 0


# ── 3.2 Location quality from loss-period dates ────────────────────────────

def test_loss_period_points_are_not_in_the_track_and_pre_loss_quality_is_kept(binary_case):
    case = binary_case
    db = case.db
    t0 = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=3)
    for minutes, position in ((0, IN_PASTURE), (5, IN_PASTURE), (60, OUTSIDE), (70, OUTSIDE), (120, IN_PASTURE)):
        when = t0 + timedelta(minutes=minutes)
        db.add(Telemetry(time=when, animal_id=case.animal.id, device_id=case.device.id, received_at=when,
                         time_source="device_utc", protocol_version=2, behavior_eligible=True,
                         latitude=position[0], longitude=position[1],
                         location=f"POINT({position[1]} {position[0]})", satellites=8, activity=0.1,
                         activity_state="lying", sample_rate=10, window_samples=150, battery_level=50))
    # Collar lost from +30 to +100 min, then remounted (status active again).
    db.add(DeviceLossPeriod(device_id=case.device.id, started_at=t0 + timedelta(minutes=30),
                            ended_at=t0 + timedelta(minutes=100), declared_at=t0, audit=[]))
    db.commit()
    history = get_location_history(db, case.animal, case.farm.id, t0 - timedelta(minutes=1), t0 + timedelta(hours=3))
    times = [ensure_minutes(p.time, t0) for segment in history.segments for p in segment.points]
    assert times == [0, 5, 120]
    assert [segment.quality for segment in history.segments] == ["reliable", "reliable"]
    assert [gap.reason for gap in history.gaps] == ["loss_period"]
    assert history.position_is_animal is True


def test_current_lost_status_without_loss_dates_does_not_degrade_quality(binary_case):
    case = binary_case
    db = case.db
    t0 = datetime.now(UTC).replace(microsecond=0) - timedelta(hours=1)
    for minutes in (0, 5):
        when = t0 + timedelta(minutes=minutes)
        db.add(Telemetry(time=when, animal_id=case.animal.id, device_id=case.device.id, received_at=when,
                         time_source="device_utc", protocol_version=2, behavior_eligible=True,
                         latitude=IN_PASTURE[0], longitude=IN_PASTURE[1], satellites=8, activity=0.1,
                         activity_state="lying", sample_rate=10, window_samples=150, battery_level=50))
    case.device.status = "lost"
    db.commit()
    history = get_location_history(db, case.animal, case.farm.id, t0 - timedelta(minutes=1), t0 + timedelta(hours=1))
    assert [segment.quality for segment in history.segments] == ["reliable"]


def ensure_minutes(moment, origin):
    return int((moment.astimezone(UTC) - origin).total_seconds() // 60)


# ── 3.3 Delete only empty animals ───────────────────────────────────────────

@pytest.fixture
def animals_client(binary_case):
    app = FastAPI()
    app.include_router(animals.router, prefix="/api/v1")
    owner = _member(binary_case.db, binary_case.farm, role="owner")
    binary_case.db.commit()
    app.dependency_overrides[get_db] = lambda: binary_case.db
    app.dependency_overrides[get_current_user] = lambda db=Depends(get_db): db.get(User, owner.id)
    with TestClient(app) as client:
        yield client


def test_animal_with_history_cannot_be_deleted(binary_case, animals_client):
    db = binary_case.db
    db.add(Alert(animal_id=binary_case.animal.id, farm_id=binary_case.farm.id, type="health",
                 severity="info", title="t", triggered_at=datetime.utcnow()))
    db.commit()
    response = animals_client.delete(f"/api/v1/animals/{binary_case.animal.id}")
    assert response.status_code == 409 and response.json()["detail"] == "animal_has_history"
    assert db.get(Animal, binary_case.animal.id) is not None


def test_empty_animal_with_only_a_tracking_period_is_deleted(binary_case, animals_client):
    db = binary_case.db
    animal = Animal(farm_id=binary_case.farm.id, name="Typo", status="active")
    db.add(animal)
    db.flush()
    db.add(AnimalTrackingPeriod(animal_id=animal.id, farm_id=binary_case.farm.id,
                                valid_from=datetime.now(UTC), source="registration"))
    db.commit()
    assert animals_client.delete(f"/api/v1/animals/{animal.id}").status_code == 204
    db.expire_all()
    assert db.get(Animal, animal.id) is None
    assert db.query(AnimalTrackingPeriod).filter_by(animal_id=animal.id).count() == 0


# ── 3.4 Case status journal ─────────────────────────────────────────────────

def test_close_then_reopen_adds_two_journal_entries(binary_case):
    db = binary_case.db
    vet = _member(db, binary_case.farm, role="vet")
    db.commit()
    case = create_veterinary_case(db, binary_case.farm.id, vet,
                                  VeterinaryCaseCreate(animal_id=binary_case.animal.id, title="Lameness"))
    update_veterinary_case(db, binary_case.farm.id, case.id, VeterinaryCaseUpdate(status="closed"), user=vet)
    closed_at = db.get(type(case), case.id).closed_at
    assert closed_at is not None
    reopened = update_veterinary_case(db, binary_case.farm.id, case.id,
                                      VeterinaryCaseUpdate(status="confirmed"), user=vet)
    update_veterinary_case(db, binary_case.farm.id, case.id, VeterinaryCaseUpdate(status="confirmed"), user=vet)
    journal = (db.query(VeterinaryEntry).filter_by(case_id=case.id, entry_type="status_change")
               .order_by(VeterinaryEntry.id).all())
    assert [entry.content for entry in journal] == ["Status: provisional → closed", "Status: closed → confirmed"]
    assert all(entry.author_user_id == vet.id for entry in journal)
    assert reopened.closed_at is None  # current state; the closing stays in the journal


# ── 3.5 Daily job lock and stale runs (default isolated engine) ────────────

def test_concurrent_daily_run_is_refused_without_a_run_row():
    target = date(1900, 1, 2)
    keys = job_tracking._lock_keys(job_tracking.DAILY_PIPELINE_JOB_NAME, target)
    holder = engine.connect()
    transaction = holder.begin()
    try:
        assert holder.execute(text("SELECT pg_try_advisory_xact_lock(:a, :b)"), {"a": keys[0], "b": keys[1]}).scalar()
        with pytest.raises(job_tracking.JobAlreadyRunning):
            job_tracking.run_daily_pipeline_tracked(target_date=target, trigger_source="manual")
        app = FastAPI()
        app.include_router(admin.router, prefix="/api/v1")
        app.dependency_overrides[require_admin] = lambda: SimpleNamespace(id=1, email="admin@example.com", role="admin")
        with TestClient(app) as client:
            response = client.post("/api/v1/admin/run-daily-jobs", params={"target_date": target.isoformat()})
            assert response.status_code == 409
    finally:
        transaction.rollback()
        holder.close()
    with SessionLocal() as db:
        assert db.query(DailyJobRun).filter_by(target_date=target).count() == 0


def test_stale_running_row_is_marked_failed_at_next_start():
    target = date(1900, 1, 3)
    with SessionLocal() as db:
        stale = DailyJobRun(job_name=job_tracking.DAILY_PIPELINE_JOB_NAME, trigger_source="scheduled",
                            target_date=target, timezone_name="Asia/Tokyo", status="running",
                            started_at=datetime.now(UTC) - timedelta(hours=3))
        recent = DailyJobRun(job_name=job_tracking.DAILY_PIPELINE_JOB_NAME, trigger_source="scheduled",
                             target_date=target, timezone_name="Asia/Tokyo", status="running",
                             started_at=datetime.now(UTC) - timedelta(minutes=30))
        db.add_all([stale, recent])
        db.commit()
        ids = (stale.id, recent.id)
    result = job_tracking.run_daily_pipeline_tracked(target_date=target, trigger_source="manual")
    with SessionLocal() as db:
        stale, recent = db.get(DailyJobRun, ids[0]), db.get(DailyJobRun, ids[1])
        assert stale.status == "failed" and stale.error_message.startswith("stale")
        assert recent.status == "running"
        assert db.get(DailyJobRun, result["job_run_id"]).status == "success"
        db.query(DailyJobRun).filter(DailyJobRun.target_date == target).delete()
        db.commit()


# ── 3.6 InvalidCredentials keeps phone tokens ──────────────────────────────

class _FakeResponse(io.BytesIO):
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


@pytest.mark.parametrize("error,deactivate", [("InvalidCredentials", False), ("DeviceNotRegistered", True)])
def test_only_token_specific_errors_deactivate(monkeypatch, error, deactivate):
    body = {"data": {"status": "error", "message": error, "details": {"error": error}}}
    monkeypatch.setattr(push_provider.urllib.request, "urlopen",
                        lambda request, timeout: _FakeResponse(json.dumps(body).encode()))
    response = ExpoPushProvider().send_push_notification(PushDevice(push_token="ExponentPushToken[x]"), "t", "b")
    assert response.success is False and response.deactivate_token is deactivate and response.retryable is False


def test_dispatch_keeps_tokens_on_invalid_credentials(binary_case, monkeypatch):
    db = binary_case.db
    member = _member(db, binary_case.farm)
    device = PushDevice(user_id=member.id, provider="expo", push_token=f"ExponentPushToken[{uuid4().hex}]", active=True)
    alert = Alert(animal_id=binary_case.animal.id, farm_id=binary_case.farm.id, type="health",
                  severity="warning", title="t", triggered_at=datetime.utcnow())
    db.add_all([device, alert])
    db.flush()
    notification_service.enqueue_alert_notification(db, alert)
    db.commit()
    body = {"data": {"status": "error", "message": "bad", "details": {"error": "InvalidCredentials"}}}
    monkeypatch.setattr(push_provider.urllib.request, "urlopen",
                        lambda request, timeout: _FakeResponse(json.dumps(body).encode()))
    notification_service.dispatch_pending_notifications(db, provider=ExpoPushProvider())
    db.refresh(device)
    delivery = db.query(NotificationDelivery).filter_by(alert_id=alert.id, user_id=member.id).one()
    assert device.active is True
    assert delivery.status == "failed" and delivery.last_error_code == "InvalidCredentials"


# ── 3.7 Danger alert lifecycle ──────────────────────────────────────────────

def test_danger_alert_records_exit_and_reentry_and_resolution_starts_a_new_alert(binary_case, monkeypatch):
    case = binary_case
    db = case.db
    _zones(db, case.farm)
    db.commit()
    now = datetime.now(UTC).replace(microsecond=0)
    monkeypatch.setattr(geofence_engine, "utc_now", lambda: now)

    def fix(offset, position):
        alerts = geofence_engine.evaluate_geofencing(case.animal, case.device, position[0], position[1], 8, 1,
                                                     now - timedelta(seconds=offset), db)
        db.commit()
        return alerts

    def danger_alerts():
        return db.query(Alert).filter_by(animal_id=case.animal.id, severity="critical").order_by(Alert.id).all()

    fix(100, IN_DANGER)
    first = danger_alerts()[0]
    inside_at = first.alert_metadata["last_detected_inside_at"]
    fix(80, IN_PASTURE)
    db.refresh(first)
    assert first.resolved_at is None
    assert first.alert_metadata["last_detected_inside_at"] == inside_at
    assert first.alert_metadata["left_zone_at"] == (now - timedelta(seconds=80)).isoformat()
    fix(60, IN_PASTURE)
    db.refresh(first)
    assert first.alert_metadata["left_zone_at"] == (now - timedelta(seconds=80)).isoformat()  # first exit kept

    fix(40, IN_DANGER)
    assert len(danger_alerts()) == 1
    db.refresh(first)
    assert first.alert_metadata["reentry_count"] == 1 and first.alert_metadata["left_zone_at"] is None
    assert first.alert_metadata["last_detected_inside_at"] == (now - timedelta(seconds=40)).isoformat()

    first.resolved_at = datetime.utcnow()  # resolved by a human only
    db.commit()
    fix(20, IN_DANGER)
    alerts = danger_alerts()
    assert len(alerts) == 2 and alerts[1].resolved_at is None and alerts[1].id != first.id


# ── 3.8 One fix, danger + pasture exit → one notification ──────────────────

def test_fix_in_danger_outside_pasture_gives_two_alerts_one_notification(binary_case, binary_client):
    case = binary_case
    db = case.db
    _zones(db, case.farm)
    _member(db, case.farm)
    db.commit()
    now = datetime.now(UTC).replace(microsecond=0)
    assert _json_fix(binary_client, case, now - timedelta(seconds=70), IN_DANGER).status_code == 201
    assert _json_fix(binary_client, case, now - timedelta(seconds=10), IN_DANGER).status_code == 201
    alerts = {(a.alert_metadata or {}).get("sub_type"): a
              for a in db.query(Alert).filter_by(animal_id=case.animal.id).all()}
    assert set(alerts) == {"danger_zone_entry", "pasture_exit"}
    assert _deliveries(db, alerts["danger_zone_entry"].id) == 1
    assert _deliveries(db, alerts["pasture_exit"].id) == 0
    assert alerts["pasture_exit"].alert_metadata[notification_service.NOTIFICATION_SUPPRESSED] == "covered_by_danger_alert"
    notification_service.dispatch_pending_notifications(db, provider=MockPushProvider())
    assert _deliveries(db, alerts["pasture_exit"].id) == 0  # reconciliation respects the suppression
