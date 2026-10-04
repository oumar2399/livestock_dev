"""Extend single tracking periods back to the animal's first telemetry window.

DEVELOPMENT DATA ONLY. Never run on real farm data without proof of provenance
(handoff rule 7: no history attributed to a farm without proven provenance).

Why: the 7b3d5f6a8c9e migration created one tracking period per animal starting at
deployment (around 2026-09-21), while development telemetry goes back to 2024. Since
B2, telemetry before valid_from is hidden from the farm.

For each animal with exactly ONE tracking period whose farm_id equals the animal's
current farm_id, valid_from becomes the start of the earliest telemetry window
(time - window_samples / sample_rate), when that is earlier than the current
valid_from. Animals with several periods, a farm mismatch, no period or no telemetry
are skipped and reported.

Everything runs in one transaction: --dry-run (default) rolls back, --apply commits.
Save the dry-run output: it is the only record of the old valid_from values.

    python scripts/backfill_tracking_periods.py --database-url URL            # dry run
    python scripts/backfill_tracking_periods.py --database-url URL --apply    # commit
"""

import argparse
import sys
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Connection

BACKFILL_SOURCE = "history_backfill"


@dataclass
class AnimalReport:
    animal_id: int
    name: str
    outcome: str  # "updated" | "unchanged" | "skipped"
    reason: str = ""
    old_valid_from: Optional[datetime] = None
    new_valid_from: Optional[datetime] = None
    telemetry_rows: int = 0
    telemetry_devices: List[str] = field(default_factory=list)
    period_device: Optional[str] = None

    @property
    def device_mismatch(self) -> bool:
        return any(device != self.period_device for device in self.telemetry_devices)


@dataclass
class BackfillReport:
    animals: List[AnimalReport]
    source_updated: bool
    source_note: str


def source_can_be_set(connection: Connection) -> tuple:
    """Return (allowed, note): refuse when any CHECK constraint mentions the source column."""
    checks = connection.execute(text("""
        SELECT conname, pg_get_constraintdef(oid)
        FROM pg_constraint
        WHERE conrelid = 'animal_tracking_periods'::regclass AND contype = 'c'
    """)).all()
    blocking = [name for name, definition in checks if "source" in definition]
    if blocking:
        return False, f"source left unchanged: CHECK constraint(s) {', '.join(blocking)} restrict it"
    length = connection.execute(text("""
        SELECT character_maximum_length FROM information_schema.columns
        WHERE table_name = 'animal_tracking_periods' AND column_name = 'source'
    """)).scalar()
    if length is not None and length < len(BACKFILL_SOURCE):
        return False, f"source left unchanged: column limited to {length} characters"
    return True, f"source set to '{BACKFILL_SOURCE}' (no CHECK constraint on the column)"


def backfill(connection: Connection) -> BackfillReport:
    """Compute and write the changes inside the caller's transaction (never commits)."""
    # Same lock as the 7b3d5f6a8c9e bootstrap: no period can appear or change meanwhile.
    connection.execute(text("LOCK TABLE animals, animal_tracking_periods IN SHARE ROW EXCLUSIVE MODE"))
    set_source, source_note = source_can_be_set(connection)

    animals = connection.execute(text("""
        SELECT a.id, a.name, a.farm_id, COUNT(p.id) AS periods
        FROM animals a
        LEFT JOIN animal_tracking_periods p ON p.animal_id = a.id
        GROUP BY a.id, a.name, a.farm_id
        ORDER BY a.id
    """)).all()

    reports = []
    for animal_id, name, animal_farm, period_count in animals:
        report = AnimalReport(animal_id=animal_id, name=name, outcome="skipped")
        reports.append(report)

        stats = connection.execute(text("""
            SELECT COUNT(*), COALESCE(array_agg(DISTINCT device_id), '{}')
            FROM telemetry WHERE animal_id = :animal
        """), {"animal": animal_id}).one()
        report.telemetry_rows = stats[0]
        report.telemetry_devices = sorted(device for device in stats[1] if device is not None)

        if period_count != 1:
            report.reason = "no tracking period" if period_count == 0 else f"{period_count} tracking periods"
            continue

        period = connection.execute(text("""
            SELECT id, farm_id, device_id, valid_from
            FROM animal_tracking_periods WHERE animal_id = :animal
        """), {"animal": animal_id}).one()
        report.old_valid_from = period.valid_from
        report.period_device = period.device_id

        if animal_farm is None or period.farm_id != animal_farm:
            report.reason = f"farm mismatch (period farm {period.farm_id}, animal farm {animal_farm})"
            continue
        if report.telemetry_rows == 0:
            report.reason = "no telemetry"
            continue

        first = connection.execute(text("""
            SELECT time, window_samples, sample_rate FROM telemetry
            WHERE animal_id = :animal ORDER BY time LIMIT 1
        """), {"animal": animal_id}).one()
        if first.window_samples and first.sample_rate and first.window_samples > 0 and first.sample_rate > 0:
            window_start = first.time - timedelta(seconds=first.window_samples / first.sample_rate)
        else:
            window_start = first.time
            report.reason = "first window duration unknown: window end used"

        if window_start >= period.valid_from:
            report.outcome = "unchanged"
            report.reason = report.reason or "telemetry starts inside the period"
            continue

        report.new_valid_from = window_start
        report.outcome = "updated"
        connection.execute(text(
            "UPDATE animal_tracking_periods SET valid_from = :start"
            + (", source = :source" if set_source else "")
            + " WHERE id = :period"
        ), {"start": window_start, "source": BACKFILL_SOURCE, "period": period.id})

    return BackfillReport(animals=reports, source_updated=set_source, source_note=source_note)


def _iso(value: Optional[datetime]) -> str:
    return value.astimezone(timezone.utc).isoformat() if value is not None else "-"


def print_report(report: BackfillReport, applied: bool, out=None) -> None:
    out = out or sys.stdout
    mode = "APPLY: changes committed" if applied else "DRY RUN: transaction rolled back, nothing written"
    print(f"backfill_tracking_periods: {mode} (times in UTC)", file=out)
    print(report.source_note, file=out)
    print("animal_id | name | outcome | old_valid_from | new_valid_from | telemetry_rows | "
          "telemetry_devices | period_device | device_mismatch | note", file=out)
    for a in report.animals:
        print(" | ".join([
            str(a.animal_id), a.name or "-", a.outcome, _iso(a.old_valid_from), _iso(a.new_valid_from),
            str(a.telemetry_rows), ",".join(a.telemetry_devices) or "-", a.period_device or "-",
            "YES" if a.device_mismatch else "no", a.reason or "-",
        ]), file=out)
    counts = {}
    for a in report.animals:
        counts[a.outcome] = counts.get(a.outcome, 0) + 1
    print("totals: " + ", ".join(f"{k}={v}" for k, v in sorted(counts.items())), file=out)
    mismatches = sum(1 for a in report.animals if a.outcome == "updated" and a.device_mismatch)
    if mismatches:
        print(f"note: {mismatches} updated animal(s) have telemetry from another device than the period's; "
              "those rows appear in history but stay excluded from farm reports.", file=out)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--database-url", required=True, help="SQLAlchemy URL of the target database")
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument("--dry-run", action="store_true", help="report only, roll back (default)")
    mode.add_argument("--apply", action="store_true", help="commit the changes")
    args = parser.parse_args(argv)

    engine = create_engine(args.database_url, hide_parameters=True)
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            try:
                report = backfill(connection)
                if args.apply:
                    transaction.commit()
                else:
                    transaction.rollback()
            except Exception:
                transaction.rollback()
                raise
        print_report(report, applied=args.apply)
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
