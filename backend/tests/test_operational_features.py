"""Focused integration checks for the low-risk operational features."""

import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.core.config import TARGET_TIMEZONE
from app.db.database import SessionLocal
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.daily_summary import DailyBehaviorSummary
from app.models.farm import Farm
from app.models.geofence import Geofence
from app.models.job_run import DailyJobRun
from app.schemas.geofence import GeoPoint
from app.services.csv_export import _csv_line
from app.services.geofence_service import build_polygon, geofence_query, serialize_geofence
from app.services.job_tracking import run_daily_pipeline_tracked
from app.services.system_health import build_system_status
from app.services.timeline import build_timeline


def test_job_tracking() -> None:
    result = run_daily_pipeline_tracked(
        target_date=date(1900, 1, 1),
        trigger_source="manual",
    )
    cleanup_db = SessionLocal()
    try:
        run = cleanup_db.get(DailyJobRun, result["job_run_id"])
        assert run is not None
        assert run.status == "success"
        assert run.timezone_name == TARGET_TIMEZONE
        assert run.finished_at is not None
        cleanup_db.delete(run)
        cleanup_db.commit()
    finally:
        cleanup_db.close()


def test_transactional_features() -> None:
    db = SessionLocal()
    try:
        farm = Farm(name="operational-feature-test")
        db.add(farm)
        db.flush()
        animal = Animal(farm_id=farm.id, name="Timeline test", species="bovine")
        db.add(animal)
        db.flush()

        points = [
            GeoPoint(latitude=35.6800, longitude=139.7600),
            GeoPoint(latitude=35.6810, longitude=139.7640),
            GeoPoint(latitude=35.6780, longitude=139.7650),
        ]
        zone = Geofence(
            farm_id=farm.id,
            name="North pasture",
            type="pasture",
            active=True,
            polygon=build_polygon(db, points),
        )
        db.add(zone)
        db.flush()
        stored_zone, geojson = geofence_query(db).filter(Geofence.id == zone.id).one()
        payload = serialize_geofence(stored_zone, geojson)
        assert payload["farm_id"] == farm.id
        assert payload["points"][0] == payload["points"][-1]

        occurred_at = datetime(2026, 8, 31, 12, 0, 0)
        db.add_all([
            Alert(
                animal_id=animal.id,
                type="health",
                severity="warning",
                title="First alert",
                triggered_at=occurred_at,
            ),
            Alert(
                animal_id=animal.id,
                type="battery",
                severity="info",
                title="Second alert",
                triggered_at=occurred_at,
            ),
            DailyBehaviorSummary(
                animal_id=animal.id,
                date=date(2026, 8, 31),
                pct_active=60.0,
                pct_resting=40.0,
                n_predictions=10,
                avg_confidence=0.9,
                created_at=occurred_at,
            ),
        ])
        db.flush()

        first_page = build_timeline(db, animal.id, None, None, None, 2, None)
        assert len(first_page.items) == 2
        assert first_page.next_cursor is not None
        second_page = build_timeline(
            db, animal.id, None, None, None, 2, first_page.next_cursor
        )
        all_ids = [item.id for item in first_page.items + second_page.items]
        assert len(all_ids) == 3
        assert len(set(all_ids)) == 3

        csv_value = _csv_line(["=SUM(1,1)", "normal"], include_bom=True)
        assert csv_value.startswith("\ufeff")
        assert "'=SUM(1,1)" in csv_value

        status = build_system_status(db)
        assert status["database"]["status"] == "up"
        assert status["schema"]["revision"] == "2c8e0f6a7b9d"
        assert status["target_timezone"] == "Asia/Tokyo"
    finally:
        db.rollback()
        db.close()


if __name__ == "__main__":
    test_job_tracking()
    test_transactional_features()
    print("ALL OPERATIONAL FEATURE TESTS PASSED!")
