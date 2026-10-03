"""Regression cases from the farm reporting/geofence audit, on disposable DB fixtures."""

from datetime import date, datetime, timedelta
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app.core.timezone import UTC, TARGET_TZ
from app.models.user import User
from app.models.farm import Farm
from app.models.device import Device
from app.models.animal import Animal
from app.models.telemetry import Telemetry
from app.models.telemetry_quality import DeviceLossPeriod
from app.models.provenance import AnimalTrackingPeriod
from app.models.geofence import Geofence
from app.services import farm_reports, geofence_engine
from app.services.telemetry_quality import eligible_clause
from app.api.v1.farms import create_farm, FarmCreate


@pytest.fixture
def tracked(binary_db):
    db = binary_db
    suffix = uuid4().hex
    user = User(email=f'{suffix}@example.com', password_hash='test', name='Review', role='admin')
    db.add(user)
    db.flush()
    farm = Farm(name='Review', owner_id=user.id)
    db.add(farm)
    db.flush()
    animals = []
    for i in range(2):
        device = Device(id=f'R-{i}-{suffix}', farm_id=farm.id, status='active')
        db.add(device)
        db.flush()
        animal = Animal(name=f'Review {i}', farm_id=farm.id, assigned_device=device.id)
        db.add(animal)
        db.flush()
        animals.append((animal, device))
    return db, user, farm, animals


def window(env, index, end, start=None, source='device_utc', device_id=None):
    db, _, farm, animals = env
    animal, device = animals[index]
    start = start or end - timedelta(seconds=15)
    db.add(AnimalTrackingPeriod(animal_id=animal.id, device_id=device.id, farm_id=farm.id,
                               valid_from=start, valid_to=end, source='registration'))
    row = Telemetry(animal_id=animal.id, device_id=device_id or device.id, time=end,
                    received_at=end, sample_rate=10, window_samples=150,
                    predicted_behavior='Active', behavior_eligible=True, time_source=source)
    db.add(row)
    db.flush()
    return row


def test_simultaneous_animals_coverage_is_additive(tracked):
    db, _, farm, _ = tracked
    end = datetime(2026, 9, 1, 12, tzinfo=UTC)
    window(tracked, 0, end)
    window(tracked, 1, end)
    summary = farm_reports.get_farm_overview_data(db, farm.id, date(2026, 9, 1), date(2026, 9, 1)).period_summary
    assert summary.dated_coverage_seconds == 30
    assert summary.proven_tracking_seconds == 30
    assert summary.dated_coverage_ratio == 1


def test_midnight_windows_are_clipped_and_exact_end_included(tracked):
    db, _, farm, _ = tracked
    midnight = datetime(2026, 9, 2, tzinfo=TARGET_TZ).astimezone(UTC)
    window(tracked, 0, midnight + timedelta(seconds=5))
    window(tracked, 1, midnight)
    quality = farm_reports.get_farm_quality_data(db, farm.id, date(2026, 9, 1), date(2026, 9, 2))
    assert [r.covered_seconds for r in quality.items] == [10, 5, 15, 0]
    previous = farm_reports.get_farm_overview_data(db, farm.id, date(2026, 9, 1), date(2026, 9, 1)).period_summary
    assert previous.dated_coverage_seconds == 25


def test_late_loss_declaration_excluded_from_both_reports(tracked):
    db, _, farm, animals = tracked
    end = datetime(2026, 9, 1, 12, tzinfo=UTC)
    window(tracked, 0, end)
    db.add(DeviceLossPeriod(device_id=animals[0][1].id, started_at=end-timedelta(hours=1),
                            declared_at=end, audit={}))
    db.flush()
    summary = farm_reports.get_farm_overview_data(db, farm.id, end.date(), end.date()).period_summary
    quality = farm_reports.get_farm_quality_data(db, farm.id, end.date(), end.date())
    assert summary.behavior_breakdown['active_count'] == 0
    assert summary.behavioral_coverage_seconds == 0
    assert quality.items[0].active_count == 0
    assert quality.items[0].exclusions_count == 1
    assert db.query(Telemetry).filter(Telemetry.device_id == animals[0][1].id, eligible_clause()).count() == 0


def test_device_identity_is_required_for_provenance(tracked):
    db, _, farm, animals = tracked
    end = datetime(2026, 9, 1, 12, tzinfo=UTC)
    window(tracked, 0, end, device_id=animals[1][1].id)
    summary = farm_reports.get_farm_overview_data(db, farm.id, end.date(), end.date()).period_summary
    assert summary.dated_windows_count == 0


@pytest.mark.parametrize('source', ['server_reception', 'unknown'])
def test_uncertain_clock_does_not_inflate_reliable_coverage(tracked, source):
    db, _, farm, _ = tracked
    end = datetime(2026, 9, 1, 12, tzinfo=UTC)
    window(tracked, 0, end, source=source)
    summary = farm_reports.get_farm_overview_data(db, farm.id, end.date(), end.date()).period_summary
    assert summary.dated_windows_count == 1
    assert summary.dated_coverage_seconds == 0
    assert summary.behavioral_coverage_seconds == 0


def test_unknown_profile_is_not_assumed_15_seconds(tracked):
    db, _, farm, _ = tracked
    end = datetime(2026, 9, 1, 12, tzinfo=UTC)
    row = window(tracked, 0, end)
    row.sample_rate = None
    row.window_samples = None
    db.flush()
    summary = farm_reports.get_farm_overview_data(db, farm.id, end.date(), end.date()).period_summary
    assert summary.dated_coverage_seconds == 0


def test_row_budget_returns_explicit_error(tracked, monkeypatch):
    db, _, farm, _ = tracked
    end = datetime(2026, 9, 1, 12, tzinfo=UTC)
    window(tracked, 0, end)
    monkeypatch.setattr(farm_reports, 'MAX_REPORT_WINDOWS', 0)
    with pytest.raises(HTTPException) as error:
        farm_reports.get_farm_overview_data(db, farm.id, end.date(), end.date())
    assert error.value.status_code == 413


def test_31_inclusive_days_maximum():
    farm_reports.validate_report_dates(date(2026, 8, 1), date(2026, 8, 31))
    with pytest.raises(HTTPException):
        farm_reports.validate_report_dates(date(2026, 8, 1), date(2026, 9, 1))


def test_farm_receipt_survives_session_reload_and_checks_all_fields(tracked):
    db, user, _, _ = tracked
    payload = FarmCreate(name='Durable', address='A', client_request_id=uuid4().hex)
    first = create_farm(payload, db, user)
    db.expire_all()
    second = create_farm(payload, db, user)
    assert second['id'] == first['id']
    changed = payload.model_copy(update={'address': 'B'})
    with pytest.raises(HTTPException) as error:
        create_farm(changed, db, user)
    assert error.value.status_code == 409


def test_concurrent_farm_creation_uses_one_durable_receipt(binary_engine):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier
    from sqlalchemy.orm import Session
    with Session(binary_engine) as db:
        user = User(email=f'{uuid4().hex}@example.com', password_hash='test', name='Concurrent', role='admin')
        db.add(user)
        db.commit()
        user_id = user.id
    payload = FarmCreate(name='Concurrent farm', client_request_id=uuid4().hex)
    barrier = Barrier(2)

    def submit(_):
        with Session(binary_engine) as db:
            user = db.get(User, user_id)
            barrier.wait(timeout=10)
            return create_farm(payload, db, user)['id']

    with ThreadPoolExecutor(max_workers=2) as pool:
        ids = list(pool.map(submit, range(2)))
    assert ids[0] == ids[1]
    with Session(binary_engine) as db:
        assert db.query(Farm).filter(Farm.owner_id == user_id).count() == 1


def test_real_postgis_geofence_ignores_old_confirmation_and_late_packets(tracked, monkeypatch):
    db, _, farm, animals = tracked
    animal, device = animals[0]
    now = datetime(2026, 9, 1, 12, tzinfo=UTC)
    monkeypatch.setattr(geofence_engine, 'utc_now', lambda: now)
    db.add(Geofence(farm_id=farm.id, name='Pasture', type='pasture', active=True,
                   polygon='SRID=4326;POLYGON((0 0,1 0,1 1,0 1,0 0))'))
    previous = Telemetry(animal_id=animal.id, device_id=device.id, time=now-timedelta(days=1),
                         latitude=2, longitude=2, satellites=8, speed=1, behavior_eligible=True)
    db.add(previous)
    db.flush()
    evaluate = lambda stamp: geofence_engine.evaluate_geofencing(animal, device, 2, 2, 8, 1, stamp, db)
    assert evaluate(now) == []
    previous.time = now - timedelta(seconds=15)
    db.flush()
    assert len(evaluate(now)) == 1
    db.flush()
    # A newer position already exists: an out-of-order point cannot change alerts.
    assert evaluate(now-timedelta(seconds=30)) == []
    assert evaluate(now-timedelta(hours=1)) == []
