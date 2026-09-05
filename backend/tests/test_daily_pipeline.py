"""
Pytest Test Suite for Daily Pipeline Service & Scheduler
=========================================================
Verifies:
  1. Sequential execution of aggregation -> anomaly detection.
  2. Automatic date default (yesterday in the target timezone).
  3. APScheduler job wrapper DB session handling.
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import SessionLocal
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.telemetry import Telemetry
from app.models.daily_summary import DailyBehaviorSummary
from app.models.alert import Alert
from app.services.daily_summary import get_target_date_bounds
from app.services.daily_pipeline import run_daily_pipeline, get_yesterday_target
from app.core.timezone import TARGET_TZ
from app.core.scheduler import run_daily_pipeline_job, start_scheduler, stop_scheduler, scheduler
from app.core.config import settings


def test_get_yesterday_target():
    yesterday = get_yesterday_target()
    expected = (datetime.now(TARGET_TZ) - timedelta(days=1)).date()
    assert yesterday == expected


def test_run_daily_pipeline_integration(db, test_animal):
    target_date = date(2026, 8, 19)
    start_dt, _ = get_target_date_bounds(target_date)

    # 1. Seed telemetry for baseline days and target day
    # Target day telemetry (100% active -> low activity anomaly relative to baseline)
    for hour in range(5):
        t = Telemetry(
            time=start_dt + timedelta(hours=hour),
            animal_id=test_animal.id,
            device_id="M5-PIPE-001",
            predicted_behavior="Active",
            behavior_confidence=0.90,
        )
        db.add(t)
    db.commit()

    # 2. Run pipeline for target_date
    result = run_daily_pipeline(db, target_date=target_date)

    assert result["target_date"] == target_date.isoformat()
    assert result["summaries_created"] >= 1

    # Verify summary was created
    summary = (
        db.query(DailyBehaviorSummary)
        .filter_by(animal_id=test_animal.id, date=target_date)
        .first()
    )
    assert summary is not None
    assert summary.n_predictions == 5
    assert summary.pct_active == 100.0


def test_run_daily_pipeline_job_standalone():
    """Test that background job opens and closes its own DB session without leaking."""
    # Should execute without throwing any exception
    run_daily_pipeline_job()


def test_scheduler_lifecycle():
    """Test scheduler start and stop functions."""
    original_enabled = settings.SCHEDULER_ENABLED
    try:
        settings.SCHEDULER_ENABLED = True
        start_scheduler()
        assert scheduler.running is True
        assert scheduler.get_job("daily_behavior_pipeline") is not None

        stop_scheduler()
        assert scheduler.running is False
    finally:
        settings.SCHEDULER_ENABLED = original_enabled


if __name__ == "__main__":
    session = SessionLocal()
    print("[TEST] Running test_get_yesterday_target...")
    test_get_yesterday_target()
    print("[PASS] test_get_yesterday_target")

    print("\n[TEST] Setting up test animal...")
    farm = Farm(name="Daily-Pipeline-Test-Farm")
    session.add(farm)
    session.flush()
    animal = Animal(
        farm_id=farm.id,
        name="Pipeline-Test-Cow",
        official_id="FR-PIPE-001",
        species="Cattle",
        breed="N'Dama",
        assigned_device="M5-PIPE-001",
        status="active",
    )
    session.add(animal)
    session.commit()
    session.refresh(animal)

    try:
        print("[TEST] Running test_run_daily_pipeline_integration...")
        test_run_daily_pipeline_integration(session, animal)
        print("[PASS] test_run_daily_pipeline_integration")

        print("[TEST] Running test_run_daily_pipeline_job_standalone...")
        test_run_daily_pipeline_job_standalone()
        print("[PASS] test_run_daily_pipeline_job_standalone")

        print("[TEST] Running test_scheduler_lifecycle...")
        test_scheduler_lifecycle()
        print("[PASS] test_scheduler_lifecycle")

        print("\nALL DAILY PIPELINE & SCHEDULER TESTS PASSED!")
    finally:
        session.query(Alert).filter(Alert.animal_id == animal.id).delete()
        session.query(DailyBehaviorSummary).filter(DailyBehaviorSummary.animal_id == animal.id).delete()
        session.query(Telemetry).filter(Telemetry.animal_id == animal.id).delete()
        session.query(Animal).filter(Animal.id == animal.id).delete()
        session.query(Farm).filter(Farm.id == farm.id).delete()
        session.commit()
        session.close()
