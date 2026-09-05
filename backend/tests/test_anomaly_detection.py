"""
Pytest Test Suite for Anomaly Detection Service (Étape 3)
"""

import sys
from pathlib import Path
from datetime import datetime, time, timedelta

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.db.database import SessionLocal
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.telemetry import Telemetry
from app.models.daily_summary import DailyBehaviorSummary
from app.models.alert import Alert
from app.schemas.alert import AlertType, AlertSeverity
from app.services.anomaly_detection import (
    has_sufficient_history,
    compute_median_and_mad,
    compute_modified_z_score,
    evaluate_animal_anomaly,
)
from app.services.daily_pipeline import get_yesterday_target


def test_median_and_mad_computation():
    values = [48.0, 50.0, 52.0, 49.0, 51.0, 50.0, 49.5, 50.5, 51.5, 49.0]
    med, mad = compute_median_and_mad(values)
    assert abs(med - 50.0) < 0.1
    assert mad >= 0.0

    # Z-score for normal value
    z_normal = compute_modified_z_score(51.0, med, mad)
    assert z_normal < 3.0

    # Z-score for extreme low value
    z_low = compute_modified_z_score(10.0, med, mad)
    assert z_low > 3.0


def test_anomaly_detection_flow():
    db = SessionLocal()
    print("[TEST] Running Anomaly Detection Flow...")

    # 1. Create a farm-scoped test animal
    farm = Farm(name="Anomaly-Detection-Test-Farm")
    db.add(farm)
    db.flush()
    animal = Animal(
        farm_id=farm.id,
        name="Marguerite-Anomaly-Test",
        official_id="FR-ANO-001",
        species="Cattle",
        breed="N'Dama",
        assigned_device="M5-ANO-001",
        status="active",
    )
    db.add(animal)
    db.commit()
    db.refresh(animal)

    target_date = get_yesterday_target()

    try:
        # -------------------------------------------------------------
        # Phase A: Test Warm-up Safeguard Blocking (< 10 distinct days)
        # -------------------------------------------------------------
        print("\n--- Phase A: Warm-up safeguard check (< 10 days) ---")
        base_time = datetime.combine(target_date, time(hour=12))
        for d in range(5): # only 5 days of telemetry
            db.add(Telemetry(
                time=base_time - timedelta(days=d),
                animal_id=animal.id,
                device_id="M5-ANO-001",
                latitude=14.69,
                longitude=-17.44,
                activity=0.5,
                activity_state="Active",
                battery_level=90,
            ))
        db.commit()

        alert_blocked = evaluate_animal_anomaly(db, animal.id, target_date)
        assert alert_blocked is None, "Should not trigger anomaly alert with < 10 days of history!"
        print("PASS: Warm-up safeguard correctly blocked anomaly evaluation for < 10 days.")

        # -------------------------------------------------------------
        # Phase B: Test Low Activity Deviation (activity_deviation_low)
        # -------------------------------------------------------------
        print("\n--- Phase B: Low Activity Deviation Test ---")
        # Add 5 more telemetry days to satisfy warm-up >= 10 days
        for d in range(5, 12):
            db.add(Telemetry(
                time=base_time - timedelta(days=d),
                animal_id=animal.id,
                device_id="M5-ANO-001",
                latitude=14.69,
                longitude=-17.44,
                activity=0.5,
                activity_state="Active",
                battery_level=90,
            ))
        db.commit()

        # Seed 10 baseline DailyBehaviorSummaries (~50% pct_active)
        for d in range(1, 11):
            db.add(DailyBehaviorSummary(
                animal_id=animal.id,
                date=target_date - timedelta(days=d),
                pct_active=50.0 + (d % 3) - 1.0, # 49%, 50%, 51%
                pct_resting=50.0,
                n_predictions=100,
                avg_confidence=0.85,
            ))

        # Target day summary at 10% pct_active (extreme low activity)
        db.add(DailyBehaviorSummary(
            animal_id=animal.id,
            date=target_date,
            pct_active=10.0,
            pct_resting=90.0,
            n_predictions=100,
            avg_confidence=0.85,
        ))
        db.commit()

        alert_low = evaluate_animal_anomaly(db, animal.id, target_date, z_threshold=3.0)
        assert alert_low is not None, "Alert should be triggered for extreme low activity!"
        assert alert_low.type == AlertType.ACTIVITY_DEVIATION_LOW.value
        assert alert_low.severity == AlertSeverity.CRITICAL.value  # Z >= 4.5
        assert "% vs habitude" in alert_low.message
        assert "-80.0%" in alert_low.message  # Native signed negative format
        
        # Verify no medical diagnosis terms in message
        for forbidden in ["maladie", "disease", "oestrus", "estrus", "boiterie", "illness"]:
            assert forbidden not in alert_low.message.lower()

        print(f"PASS: Low activity alert generated: [{alert_low.severity}] {alert_low.message}")

        # Test Idempotency: re-running should return existing alert without duplicating
        alert_repeat = evaluate_animal_anomaly(db, animal.id, target_date)
        assert alert_repeat.id == alert_low.id
        print("PASS: Idempotency verified (no duplicate alert created).")

        # -------------------------------------------------------------
        # Phase C: Test High Activity Deviation (activity_deviation_high)
        # -------------------------------------------------------------
        print("\n--- Phase C: High Activity Deviation Test ---")
        target_date_high = target_date + timedelta(days=1)

        # Target day summary at 85% pct_active (extreme high activity vs ~50% baseline)
        db.add(DailyBehaviorSummary(
            animal_id=animal.id,
            date=target_date_high,
            pct_active=85.0,
            pct_resting=15.0,
            n_predictions=100,
            avg_confidence=0.85,
        ))
        db.commit()

        alert_high = evaluate_animal_anomaly(db, animal.id, target_date_high, z_threshold=3.0)
        assert alert_high is not None, "Alert should be triggered for extreme high activity!"
        assert alert_high.type == AlertType.ACTIVITY_DEVIATION_HIGH.value
        assert alert_high.severity == AlertSeverity.CRITICAL.value  # Symmetric severity!
        assert "+70.0%" in alert_high.message or "+70" in alert_high.message

        print(f"PASS: High activity alert generated: [{alert_high.severity}] {alert_high.message}")

        # -------------------------------------------------------------
        # Phase D: Test Zero Median Guard (% vs pts)
        # -------------------------------------------------------------
        print("\n--- Phase D: Zero Median Guard Test ---")
        animal_zero = Animal(
            farm_id=farm.id,
            name="Marguerite-ZeroMedian-Test",
            official_id="FR-ZERO-001",
            species="Cattle",
            breed="N'Dama",
            assigned_device="M5-ZERO-001",
            status="active",
        )
        db.add(animal_zero)
        db.commit()
        db.refresh(animal_zero)

        # 10 days telemetry for warm-up
        for d in range(10):
            db.add(Telemetry(
                time=base_time - timedelta(days=d),
                animal_id=animal_zero.id,
                device_id="M5-ZERO-001",
                latitude=14.69,
                longitude=-17.44,
                activity=0.0,
                activity_state="Resting",
                battery_level=90,
            ))
        # 10 baseline summaries with pct_active = 0.0 (median = 0)
        for d in range(1, 11):
            db.add(DailyBehaviorSummary(
                animal_id=animal_zero.id,
                date=target_date - timedelta(days=d),
                pct_active=0.0,
                pct_resting=100.0,
                n_predictions=100,
                avg_confidence=0.90,
            ))
        # Target day with pct_active = 15.0
        db.add(DailyBehaviorSummary(
            animal_id=animal_zero.id,
            date=target_date,
            pct_active=15.0,
            pct_resting=85.0,
            n_predictions=100,
            avg_confidence=0.90,
        ))
        db.commit()

        alert_zero = evaluate_animal_anomaly(db, animal_zero.id, target_date, z_threshold=3.0)
        assert alert_zero is not None
        assert alert_zero.type == AlertType.ACTIVITY_DEVIATION_HIGH.value
        assert "pts vs habitude" in alert_zero.message
        assert "+15.0 pts" in alert_zero.message

        print(f"PASS: Zero median alert generated: {alert_zero.message}")

    finally:
        # Cleanup test data
        test_ids = [animal.id]
        if 'animal_zero' in locals() and animal_zero.id:
            test_ids.append(animal_zero.id)

        db.query(Alert).filter(Alert.animal_id.in_(test_ids)).delete(synchronize_session=False)
        db.query(Telemetry).filter(Telemetry.animal_id.in_(test_ids)).delete(synchronize_session=False)
        db.query(DailyBehaviorSummary).filter(DailyBehaviorSummary.animal_id.in_(test_ids)).delete(synchronize_session=False)
        db.query(Animal).filter(Animal.id.in_(test_ids)).delete(synchronize_session=False)
        db.query(Farm).filter(Farm.id == farm.id).delete()
        db.commit()
        db.close()


if __name__ == "__main__":
    test_median_and_mad_computation()
    print("[PASS] test_median_and_mad_computation")
    test_anomaly_detection_flow()
    print("\nALL ANOMALY DETECTION TESTS PASSED SUCCESSFULLY!")
