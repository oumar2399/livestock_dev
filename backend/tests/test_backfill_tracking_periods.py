"""Admin backfill of tracking periods (scripts/backfill_tracking_periods.py)."""

import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

import pytest
from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import backfill_tracking_periods as script  # noqa: E402
from app.db import database  # noqa: E402
from app.models.animal import Animal  # noqa: E402
from app.models.device import Device  # noqa: E402
from app.models.farm import Farm  # noqa: E402
from app.models.provenance import AnimalTrackingPeriod  # noqa: E402
from app.models.telemetry import Telemetry  # noqa: E402
from app.models.user import User  # noqa: E402

DEPLOYED = datetime(2026, 9, 21, 12, 0, tzinfo=timezone.utc)
FIRST = datetime(2024, 5, 1, 8, 0, 15, tzinfo=timezone.utc)


def _world(db):
    suffix = uuid4().hex[:8]
    user = User(email=f"backfill-{suffix}@example.com", password_hash="x", name="Owner", role="owner")
    db.add(user)
    db.flush()
    farm = Farm(owner_id=user.id, name=f"Farm {suffix}")
    other = Farm(owner_id=user.id, name=f"Other {suffix}")
    db.add_all([farm, other])
    db.flush()
    devices = [Device(id=f"BF-{suffix}-{i}", farm_id=farm.id) for i in range(2)]
    db.add_all(devices)
    db.flush()
    return suffix, farm, other, devices


def _animal(db, farm, suffix, label, device=None, periods=(), telemetry=()):
    animal = Animal(farm_id=farm.id, name=label, official_id=f"BF-{suffix}-{label}", species="bovine",
                    status="active")
    db.add(animal)
    db.flush()
    for period_farm, start, end in periods:
        db.add(AnimalTrackingPeriod(animal_id=animal.id, device_id=device.id if device else None,
                                    farm_id=period_farm.id, valid_from=start, valid_to=end,
                                    recorded_at=start, source="deployment_bootstrap"))
    for moment, telemetry_device, samples in telemetry:
        db.add(Telemetry(time=moment, animal_id=animal.id, device_id=telemetry_device.id, received_at=moment,
                         activity=0.1, sample_rate=10 if samples else None, window_samples=samples))
    db.flush()
    return animal


def _period(db, animal):
    return db.execute(text("SELECT valid_from, source FROM animal_tracking_periods WHERE animal_id = :a"),
                      {"a": animal.id}).one()


def test_backfill_extends_single_matching_periods_and_reports_skips(db):
    suffix, farm, other, (main_device, other_device) = _world(db)
    eligible = _animal(db, farm, suffix, "eligible", main_device, [(farm, DEPLOYED, None)],
                       [(FIRST, other_device, 150), (FIRST + timedelta(days=1), main_device, 150),
                        (DEPLOYED + timedelta(hours=1), main_device, 150)])
    no_duration = _animal(db, farm, suffix, "no-duration", main_device, [(farm, DEPLOYED, None)],
                          [(FIRST, main_device, None)])
    several = _animal(db, farm, suffix, "several", main_device,
                      [(farm, DEPLOYED - timedelta(days=10), DEPLOYED), (farm, DEPLOYED, None)],
                      [(FIRST, main_device, 150)])
    mismatch = _animal(db, farm, suffix, "mismatch", main_device, [(other, DEPLOYED, None)],
                       [(FIRST, main_device, 150)])
    silent = _animal(db, farm, suffix, "silent", main_device, [(farm, DEPLOYED, None)])
    later = _animal(db, farm, suffix, "later", main_device, [(farm, DEPLOYED, None)],
                    [(DEPLOYED + timedelta(minutes=5), main_device, 150)])
    unproven = _animal(db, farm, suffix, "unproven", main_device, [], [(FIRST, main_device, 150)])

    report = script.backfill(db.connection())
    by_id = {a.animal_id: a for a in report.animals}

    row = by_id[eligible.id]
    assert row.outcome == "updated"
    assert row.old_valid_from == DEPLOYED
    # First window starts 150 / 10 = 15 s before its end timestamp.
    assert row.new_valid_from == FIRST - timedelta(seconds=15)
    assert row.telemetry_rows == 3
    assert row.telemetry_devices == sorted([main_device.id, other_device.id])
    assert row.period_device == main_device.id and row.device_mismatch
    assert _period(db, eligible) == (FIRST - timedelta(seconds=15), script.BACKFILL_SOURCE)
    assert report.source_updated

    assert by_id[no_duration.id].outcome == "updated"
    assert by_id[no_duration.id].new_valid_from == FIRST
    assert "duration unknown" in by_id[no_duration.id].reason
    assert not by_id[no_duration.id].device_mismatch

    assert (by_id[several.id].outcome, by_id[several.id].reason) == ("skipped", "2 tracking periods")
    assert by_id[mismatch.id].outcome == "skipped" and "farm mismatch" in by_id[mismatch.id].reason
    assert (by_id[silent.id].outcome, by_id[silent.id].reason) == ("skipped", "no telemetry")
    assert (by_id[unproven.id].outcome, by_id[unproven.id].reason) == ("skipped", "no tracking period")
    assert by_id[later.id].outcome == "unchanged"

    for untouched in (several, mismatch, silent, later):
        assert all(source == "deployment_bootstrap" for _, source in db.execute(text(
            "SELECT valid_from, source FROM animal_tracking_periods WHERE animal_id = :a"),
            {"a": untouched.id}).all())
    assert _period(db, mismatch).valid_from == DEPLOYED
    assert _period(db, later).valid_from == DEPLOYED


def test_command_line_dry_run_rolls_back_and_apply_commits(capsys):
    url = database.engine.url.render_as_string(hide_password=False)
    session = database.SessionLocal()
    try:
        suffix, farm, _, (device, _) = _world(session)
        animal = _animal(session, farm, suffix, "cli", device, [(farm, DEPLOYED, None)], [(FIRST, device, 150)])
        session.commit()

        assert script.main(["--database-url", url]) == 0
        out = capsys.readouterr().out
        assert "DRY RUN" in out and f"{animal.id} | cli | updated" in out
        session.expire_all()
        assert _period(session, animal) == (DEPLOYED, "deployment_bootstrap")

        assert script.main(["--database-url", url, "--apply"]) == 0
        assert "APPLY" in capsys.readouterr().out
        session.expire_all()
        assert _period(session, animal) == (FIRST - timedelta(seconds=15), script.BACKFILL_SOURCE)
    finally:
        session.rollback()
        for statement in (
            "DELETE FROM telemetry WHERE device_id LIKE :p",
            "DELETE FROM animal_tracking_periods WHERE animal_id IN (SELECT id FROM animals WHERE official_id LIKE :p)",
            "DELETE FROM animals WHERE official_id LIKE :p",
            "DELETE FROM devices WHERE id LIKE :p",
            "DELETE FROM farms WHERE name LIKE :n",
            "DELETE FROM users WHERE email LIKE :e",
        ):
            session.execute(text(statement), {"p": f"BF-{suffix}-%", "n": f"%{suffix}", "e": f"backfill-{suffix}@%"})
        session.commit()
        session.close()


def test_command_line_requires_database_url():
    with pytest.raises(SystemExit) as exit_info:
        script.main([])
    assert exit_info.value.code == 2
    with pytest.raises(SystemExit):
        script.main(["--database-url", "postgresql://x/y", "--dry-run", "--apply"])
