"""
Tests unitaires pour le service de localisation et d'historique GPS (Lot B).
"""
from datetime import datetime, timedelta
import pytest
from geoalchemy2.elements import WKTElement

from app.core.timezone import UTC, utc_now
from app.models.animal import Animal
from app.models.device import Device
from app.models.farm import Farm
from app.models.provenance import AnimalTrackingPeriod
from app.models.telemetry import Telemetry
from app.models.telemetry_quality import DeviceLossPeriod
from app.models.user import User
from app.schemas.location import TrackPoint
from app.services.location_service import (
    GAP_THRESHOLD_SECONDS,
    _classify_gap,
    _freshness_label,
    _is_valid_coord,
    _segment_track,
    _build_segment,
    get_current_location,
    get_location_history,
)


def test_is_valid_coord():
    assert _is_valid_coord(0.0, 0.0) is True
    assert _is_valid_coord(45.5, -73.5) is True
    assert _is_valid_coord(90.0, 180.0) is True
    assert _is_valid_coord(-90.0, -180.0) is True

    # Invalid coordinates
    assert _is_valid_coord(None, 0.0) is False
    assert _is_valid_coord(0.0, None) is False
    assert _is_valid_coord(91.0, 0.0) is False
    assert _is_valid_coord(-91.0, 0.0) is False
    assert _is_valid_coord(0.0, 181.0) is False
    assert _is_valid_coord(0.0, -181.0) is False


def test_freshness_label():
    assert _freshness_label(0) == "recent"
    assert _freshness_label(150) == "recent"
    assert _freshness_label(299) == "recent"
    assert _freshness_label(300) == "stale"
    assert _freshness_label(1799) == "stale"
    assert _freshness_label(1800) == "old"
    assert _freshness_label(86400) == "old"


def test_classify_gap():
    t1 = datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC)
    t2 = datetime(2026, 9, 22, 10, 45, 0, tzinfo=UTC)

    # Gap normal (sans loss_period) -> no_data
    gap = _classify_gap(t1, t2, loss_periods=[])
    assert gap.reason == "no_data"
    assert gap.duration_seconds == 45 * 60

    # Gap chevauchant une période de perte déclarée -> loss_period
    lp = DeviceLossPeriod(
        device_id="DEV-1",
        started_at=datetime(2026, 9, 22, 9, 30, 0, tzinfo=UTC),
        ended_at=datetime(2026, 9, 22, 11, 0, 0, tzinfo=UTC),
        declared_at=datetime(2026, 9, 22, 9, 30, 0, tzinfo=UTC),
        audit={"reason": "battery"},
    )
    gap_loss = _classify_gap(t1, t2, loss_periods=[lp])
    assert gap_loss.reason == "loss_period"


def test_segment_track_empty():
    start = datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 22, 12, 0, 0, tzinfo=UTC)
    segments, gaps = _segment_track([], [], start, end)

    assert len(segments) == 0
    assert len(gaps) == 1
    assert gaps[0].reason == "no_data"
    assert gaps[0].duration_seconds == 7200


def test_segment_track_with_gaps():
    start = datetime(2026, 9, 22, 10, 0, 0, tzinfo=UTC)
    end = datetime(2026, 9, 22, 14, 0, 0, tzinfo=UTC)

    p1 = TrackPoint(
        latitude=45.0,
        longitude=5.0,
        time=start + timedelta(minutes=10),
        speed=2.0,
        satellites=8,
        is_reliable=True,
    )
    p2 = TrackPoint(
        latitude=45.01,
        longitude=5.01,
        time=start + timedelta(minutes=15),
        speed=1.5,
        satellites=9,
        is_reliable=True,
    )
    p3 = TrackPoint(
        latitude=45.05,
        longitude=5.05,
        time=start + timedelta(minutes=90),  # Gap > 30m
        speed=0.5,
        satellites=7,
        is_reliable=True,
    )

    segments, gaps = _segment_track([p1, p2, p3], [], start, end)

    assert len(segments) == 2
    assert len(segments[0].points) == 2
    assert len(segments[1].points) == 1
    assert len(gaps) == 1
    assert gaps[0].duration_seconds == 75 * 60  # 90m - 15m


def test_get_current_location_db(db):
    now = utc_now()
    user = User(email="test_loc@example.com", password_hash="hash", name="User")
    db.add(user)
    db.commit()

    farm = Farm(name="Ferme Loc", owner_id=user.id)
    db.add(farm)
    db.commit()

    device = Device(id="DEV-LOC-01", farm_id=farm.id, model="M5Stack", status="active")
    db.add(device)
    db.commit()

    animal = Animal(name="Marguerite", species="cattle", farm_id=farm.id, status="active", assigned_device="DEV-LOC-01")
    db.add(animal)
    db.commit()

    # Période de tracking valide
    tracking = AnimalTrackingPeriod(
        animal_id=animal.id,
        device_id="DEV-LOC-01",
        farm_id=farm.id,
        valid_from=now - timedelta(days=5),
        valid_to=None,
        source="collar_assignment",
    )
    db.add(tracking)

    # Télémétrie avec position GPS
    telem = Telemetry(
        animal_id=animal.id,
        time=now - timedelta(minutes=2),
        device_id="DEV-LOC-01",
        latitude=45.123,
        longitude=5.456,
        location=WKTElement("POINT(5.456 45.123)", srid=4326),
        speed=1.2,
        satellites=8,
    )
    db.add(telem)
    db.commit()

    loc = get_current_location(db, animal, farm.id)
    assert loc is not None
    assert loc.animal_id == animal.id
    assert loc.animal_name == "Marguerite"
    assert loc.latitude == pytest.approx(45.123)
    assert loc.longitude == pytest.approx(5.456)
    assert loc.position_is_animal is True
    assert loc.freshness == "recent"


def test_get_current_location_lost_collar(db):
    now = utc_now()
    user = User(email="test_lost@example.com", password_hash="hash", name="User")
    db.add(user)
    db.commit()

    farm = Farm(name="Ferme Lost", owner_id=user.id)
    db.add(farm)
    db.commit()

    # Device marqué 'lost'
    device = Device(id="DEV-LOST-01", farm_id=farm.id, model="M5Stack", status="lost")
    db.add(device)
    db.commit()

    animal = Animal(name="Bella", species="cattle", farm_id=farm.id, status="active", assigned_device="DEV-LOST-01")
    db.add(animal)
    db.commit()

    tracking = AnimalTrackingPeriod(
        animal_id=animal.id,
        device_id="DEV-LOST-01",
        farm_id=farm.id,
        valid_from=now - timedelta(days=5),
        valid_to=None,
        source="collar_assignment",
    )
    db.add(tracking)

    # Collar lost 5 minutes ago (loss period dates). The point before the loss is
    # the animal's last position; the point inside the loss period is equipment only.
    db.add(DeviceLossPeriod(device_id="DEV-LOST-01", started_at=now - timedelta(minutes=5),
                            declared_at=now, audit=[]))
    for minutes, latitude in ((10, 46.0), (2, 47.0)):
        db.add(Telemetry(
            animal_id=animal.id,
            time=now - timedelta(minutes=minutes),
            device_id="DEV-LOST-01",
            latitude=latitude,
            longitude=6.0,
            location=WKTElement(f"POINT(6.0 {latitude})", srid=4326),
        ))
    db.commit()

    loc = get_current_location(db, animal, farm.id)
    assert loc is not None
    assert loc.latitude == 46.0  # loss-period point excluded
    assert loc.position_is_animal is True
    assert loc.device_status == "lost"


def test_get_location_history(db):
    now = utc_now()
    user = User(email="test_hist@example.com", password_hash="hash", name="User")
    db.add(user)
    db.commit()

    farm = Farm(name="Ferme Hist", owner_id=user.id)
    db.add(farm)
    db.commit()

    device = Device(id="DEV-HIST-01", farm_id=farm.id, model="M5Stack", status="active")
    db.add(device)
    db.commit()

    animal = Animal(name="Noiraude", species="cattle", farm_id=farm.id, status="active", assigned_device="DEV-HIST-01")
    db.add(animal)
    db.commit()

    tracking = AnimalTrackingPeriod(
        animal_id=animal.id,
        device_id="DEV-HIST-01",
        farm_id=farm.id,
        valid_from=now - timedelta(hours=10),
        valid_to=None,
        source="collar_assignment",
    )
    db.add(tracking)

    # 3 points de télémétrie sur les 3 dernières heures
    t1 = now - timedelta(hours=3)
    t2 = now - timedelta(hours=2, minutes=50)  # 10 min après t1
    t3 = now - timedelta(hours=1)             # 1h50 après t2 (gap > 30m)

    for t, lat, lon in [(t1, 45.1, 5.1), (t2, 45.12, 5.12), (t3, 45.2, 5.2)]:
        db.add(Telemetry(
            animal_id=animal.id,
            time=t,
            device_id="DEV-HIST-01",
            latitude=lat,
            longitude=lon,
            location=WKTElement(f"POINT({lon} {lat})", srid=4326),
            satellites=7,
            speed=1.0,
        ))
    db.commit()

    start = now - timedelta(hours=4)
    end = now
    history = get_location_history(db, animal, farm.id, start, end)

    assert history.animal_id == animal.id
    assert history.total_points == 3
    assert len(history.segments) == 2
    assert history.proven_coverage_ratio is not None
    assert history.proven_coverage_ratio > 0
