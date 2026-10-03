"""
Manual check for the anomaly detection warm-up safeguard.
Inserts test telemetry records across multiple days for a test animal
and asserts that has_sufficient_history() returns False for < 10 days and True for >= 10 days.

Writes to the database it is given. The URL is mandatory and must name a
disposable database (same prefixes as backend/tests/conftest.py):

    python scripts/test_anomaly_warmup.py --database-url postgresql://.../livestock_audit_xxx
"""

import argparse
import os
import sys
from pathlib import Path
from datetime import datetime, timedelta

from sqlalchemy.engine import make_url

# Add backend directory to path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

ALLOWED_DATABASE_PREFIXES = (
    "livestock_review_",
    "livestock_binary_test_",
    "livestock_audit_",
    "livestock_schema_check_",
)


def run_test():
    from app.db.database import SessionLocal
    from app.models.animal import Animal
    from app.models.farm import Farm
    from app.models.telemetry import Telemetry
    from app.services.anomaly_detection import has_sufficient_history

    db = SessionLocal()
    print("[TEST] Running Anomaly Detection Warm-up Test...")

    # 1. Create a farm-scoped test animal
    farm = Farm(name="Anomaly-Warmup-Test-Farm")
    db.add(farm)
    db.flush()
    test_animal = Animal(
        farm_id=farm.id,
        name="Marguerite-Test-FR001",
        official_id="FR001-TEST",
        species="Cattle",
        breed="N'Dama",
        assigned_device="M5-001",
        status="active",
    )
    db.add(test_animal)
    db.commit()
    db.refresh(test_animal)
    print(f"Created test animal: {test_animal.name} (ID: {test_animal.id})")

    try:
        # Phase 1: Insert telemetry for 5 distinct days
        print("\n--- Phase 1: Testing with 5 distinct days ---")
        base_time = datetime.utcnow()
        for day in range(5):
            record_time = base_time - timedelta(days=day)
            t = Telemetry(
                time=record_time,
                animal_id=test_animal.id,
                device_id="M5-001",
                latitude=14.6937,
                longitude=-17.4441,
                activity=0.5,
                activity_state="Active",
                battery_level=90,
            )
            db.add(t)
        db.commit()

        result_5 = has_sufficient_history(db, test_animal.id, min_days=10, max_window_days=20)
        print(f"Result with 5 days: {result_5}")
        assert result_5 is False, "Expected False for 5 days of history!"
        print("PASS: 5 days correctly evaluated as False (insufficient history)")

        # Phase 2: Insert telemetry for 5 more distinct days (total 10 days)
        print("\n--- Phase 2: Testing with 10 distinct days ---")
        for day in range(5, 10):
            record_time = base_time - timedelta(days=day)
            t = Telemetry(
                time=record_time,
                animal_id=test_animal.id,
                device_id="M5-001",
                latitude=14.6937,
                longitude=-17.4441,
                activity=0.5,
                activity_state="Active",
                battery_level=90,
            )
            db.add(t)
        db.commit()

        result_10 = has_sufficient_history(db, test_animal.id, min_days=10, max_window_days=20)
        print(f"Result with 10 days: {result_10}")
        assert result_10 is True, "Expected True for 10 days of history!"
        print("PASS: 10 days correctly evaluated as True (sufficient history)")

        print("\nALL WARM-UP SAFEGUARD TESTS PASSED!")

    finally:
        # Clean up test telemetry and animal
        db.query(Telemetry).filter(Telemetry.animal_id == test_animal.id).delete()
        db.query(Animal).filter(Animal.id == test_animal.id).delete()
        db.query(Farm).filter(Farm.id == farm.id).delete()
        db.commit()
        db.close()


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    parser.add_argument("--database-url", required=True, help="URL of a disposable database")
    args = parser.parse_args(argv)
    database = make_url(args.database_url).database or ""
    if not database.startswith(ALLOWED_DATABASE_PREFIXES):
        parser.error(
            f"refusing database {database!r}; allowed prefixes: {', '.join(ALLOWED_DATABASE_PREFIXES)}"
        )
    # Must be set before app.core.config is imported; load_dotenv never overrides it.
    os.environ["DATABASE_URL"] = args.database_url
    run_test()


if __name__ == "__main__":
    main()
