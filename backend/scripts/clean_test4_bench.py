#!/usr/bin/env python3
"""Explicit Test 4 cleanup. Preview by default; never run during import."""

import argparse
from pathlib import Path
import sys

BACKEND_DIR = Path(__file__).resolve().parent.parent
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session
from app.models.device import Device
from app.models.animal import Animal
from app.models.farm import Farm
from app.models.telemetry import Telemetry


def clean_bench(db, animal_id, farm_id, transport_id, expected_database, apply=False):
    if expected_database not in ("livestock_bench", "livestock_dev"):
        raise ValueError("Only the dedicated bench or historical dev bench is supported")
    if db.execute(text("SELECT current_database()")).scalar() != expected_database:
        raise ValueError("Database identity mismatch; no cleanup performed")
    device = db.query(Device).filter(Device.id == "M5-TEST4-BENCH").one_or_none()
    animal = db.query(Animal).filter(Animal.id == animal_id).one_or_none()
    farm = db.query(Farm).filter(Farm.id == farm_id).one_or_none()
    if not (device and animal and farm and
            device.transport_id == transport_id and device.farm_id == farm_id and
            animal.assigned_device == device.id and animal.farm_id == farm_id and
            animal.name == "Vache-Banc-T4" and farm.name == "Ferme-Banc-Test4"):
        raise ValueError("Bench identities do not match; no cleanup performed")
    shared = db.query(Animal).filter(
        Animal.assigned_device == device.id, Animal.id != animal_id).count()
    foreign_rows = db.query(Telemetry).filter(
        (Telemetry.device_id == device.id) | (Telemetry.animal_id == animal_id)
    ).filter(
        (Telemetry.device_id.is_(None)) |
        (Telemetry.device_id != device.id) | (Telemetry.animal_id != animal_id)
    ).count()
    if shared or foreign_rows:
        raise ValueError("Bench identity is shared with other data; manual review required")
    rows = db.query(Telemetry).filter(
        Telemetry.animal_id == animal_id, Telemetry.device_id == device.id)
    count = rows.count()
    print("PREVIEW telemetry=%d animal=%s device=%s farm=%s (farm retained)" % (
        count, animal_id, device.id, farm_id))
    if apply:
        rows.delete(synchronize_session=False)
        db.delete(animal)
        db.flush()
        db.delete(device)
        db.commit()
        print("Cleanup committed. Farm and owner retained.")
    else:
        db.rollback()
        print("Preview only. Pass --apply after checking these identities.")
    return count


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--database-url", required=True)
    parser.add_argument("--expected-database", choices=("livestock_bench", "livestock_dev"), required=True)
    parser.add_argument("--animal-id", type=int, required=True)
    parser.add_argument("--farm-id", type=int, required=True)
    parser.add_argument("--transport-id", type=int, default=102)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args(argv)
    engine = create_engine(args.database_url, hide_parameters=True)
    try:
        with Session(engine) as db:
            clean_bench(db, args.animal_id, args.farm_id, args.transport_id,
                        args.expected_database, args.apply)
    finally:
        engine.dispose()


if __name__ == "__main__":
    main()
