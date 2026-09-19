"""Explicit administrator operation for pending archive predictions, never training."""

import argparse
from app.db.database import SessionLocal
from app.services.ml_inference import load_model
from app.services.untimed_telemetry import classify_pending


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--limit", type=int, default=100)
    args = parser.parse_args()
    if not 1 <= args.limit <= 1000:
        parser.error("--limit must be between 1 and 1000")
    load_model()
    with SessionLocal() as db:
        print(classify_pending(db, limit=args.limit))


if __name__ == "__main__":
    main()
