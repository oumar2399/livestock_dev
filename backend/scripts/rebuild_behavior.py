"""Run pending quality corrections without emitting historical alert notifications."""

from app.db.database import SessionLocal
from app.services.telemetry_quality import process_behavior_rebuilds


def main():
    with SessionLocal() as db:
        try:
            print("Rebuilt summaries:", process_behavior_rebuilds(db))
        except Exception:
            db.rollback()
            raise


if __name__ == "__main__":
    main()
