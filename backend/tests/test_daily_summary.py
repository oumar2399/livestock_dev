"""
Pytest Test Suite for DailyBehaviorSummary Aggregation Service
"""

import sys
from pathlib import Path
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# Add backend root to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import SessionLocal
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.telemetry import Telemetry
from app.models.daily_summary import DailyBehaviorSummary
from app.services.daily_summary import (
    get_target_date_bounds,
    aggregate_daily_behavior,
    aggregate_all_daily_behaviors,
)
from app.core.timezone import TARGET_TZ


def get_db():
    session = SessionLocal()
    return session


def test_target_date_bounds():
    target_date = date(2026, 8, 19)
    start_dt, end_dt = get_target_date_bounds(target_date)

    assert start_dt.tzinfo == TARGET_TZ
    assert end_dt.tzinfo == TARGET_TZ
    assert start_dt.hour == 0 and start_dt.minute == 0 and start_dt.second == 0
    assert end_dt.hour == 23 and end_dt.minute == 59 and end_dt.second == 59


def test_aggregate_daily_behavior(db, test_animal):
    target_date = date(2026, 8, 19)
    start_dt, _ = get_target_date_bounds(target_date)

    # 1. Seed 4 telemetry records (3 Active, 1 Resting, 1 with None predicted_behavior)
    t1 = Telemetry(
        time=start_dt + timedelta(hours=1),
        animal_id=test_animal.id,
        device_id="M5-SUM-001",
        predicted_behavior="Active",
        behavior_confidence=0.90,
    )
    t2 = Telemetry(
        time=start_dt + timedelta(hours=2),
        animal_id=test_animal.id,
        device_id="M5-SUM-001",
        predicted_behavior="Active",
        behavior_confidence=0.80,
    )
    t3 = Telemetry(
        time=start_dt + timedelta(hours=3),
        animal_id=test_animal.id,
        device_id="M5-SUM-001",
        predicted_behavior="Active",
        behavior_confidence=0.70,
    )
    t4 = Telemetry(
        time=start_dt + timedelta(hours=4),
        animal_id=test_animal.id,
        device_id="M5-SUM-001",
        predicted_behavior="Resting",
        behavior_confidence=0.80,
    )
    # This record should be IGNORED because predicted_behavior is None
    t_ignored = Telemetry(
        time=start_dt + timedelta(hours=5),
        animal_id=test_animal.id,
        device_id="M5-SUM-001",
        predicted_behavior=None,
        activity_state="Active",
        behavior_confidence=None,
    )

    db.add_all([t1, t2, t3, t4, t_ignored])
    db.commit()

    # 2. Run aggregation
    summary = aggregate_daily_behavior(db, test_animal.id, target_date)

    assert summary is not None
    assert summary.animal_id == test_animal.id
    assert summary.date == target_date
    assert summary.n_predictions == 4  # 4 valid predictions (t_ignored was excluded)
    assert summary.pct_active == 75.0  # 3/4 = 75%
    assert summary.pct_resting == 25.0  # 1/4 = 25%
    assert abs(summary.avg_confidence - 0.80) < 0.01  # (0.9 + 0.8 + 0.7 + 0.8) / 4 = 0.80

    # 3. Test Upsert / Idempotency: re-running aggregation on same date should update, not error
    summary_again = aggregate_daily_behavior(db, test_animal.id, target_date)
    assert summary_again.id == summary.id
    assert summary_again.n_predictions == 4


def test_aggregate_daily_behavior_zero_predictions(db, test_animal):
    target_date = date(2026, 8, 18)  # Empty date with no telemetry

    summary = aggregate_daily_behavior(db, test_animal.id, target_date)

    assert summary is None
    count = db.query(DailyBehaviorSummary).filter_by(animal_id=test_animal.id, date=target_date).count()
    assert count == 0


if __name__ == "__main__":
    session = SessionLocal()
    print("[TEST] Running test_target_date_bounds...")
    test_target_date_bounds()
    print("[PASS] test_target_date_bounds")

    print("\n[TEST] Setting up test animal...")
    farm = Farm(name="Daily-Summary-Test-Farm")
    session.add(farm)
    session.flush()
    animal = Animal(
        farm_id=farm.id,
        name="Marguerite-Summary-Test",
        official_id="FR-SUM-001",
        species="Cattle",
        breed="N'Dama",
        assigned_device="M5-SUM-001",
        status="active",
    )
    session.add(animal)
    session.commit()
    session.refresh(animal)

    try:
        print("[TEST] Running test_aggregate_daily_behavior...")
        test_aggregate_daily_behavior(session, animal)
        print("[PASS] test_aggregate_daily_behavior")

        print("[TEST] Running test_aggregate_daily_behavior_zero_predictions...")
        test_aggregate_daily_behavior_zero_predictions(session, animal)
        print("[PASS] test_aggregate_daily_behavior_zero_predictions")

        print("\nALL DAILY BEHAVIOR SUMMARY TESTS PASSED!")
    finally:
        session.query(Telemetry).filter(Telemetry.animal_id == animal.id).delete()
        session.query(DailyBehaviorSummary).filter(DailyBehaviorSummary.animal_id == animal.id).delete()
        session.query(Animal).filter(Animal.id == animal.id).delete()
        session.query(Farm).filter(Farm.id == farm.id).delete()
        session.commit()
        session.close()
