"""Anomaly scoring regression tests (fix plan 7.5, 7.6, 7.7).

Each day has 100 Resting/Active windows, so one Active window = 1 percentage point.
Daily summaries come from the real aggregation; runs on the disposable database of
the binary_* fixtures.
"""

from datetime import datetime, time, timedelta, timezone
from uuid import uuid4

import pytest

from app.core.config import settings
from app.core.timezone import TARGET_TZ
from app.models.alert import Alert
from app.models.animal import Animal
from app.models.device import Device
from app.models.telemetry import Telemetry
from app.services import anomaly_detection as ad
from app.services.daily_summary import aggregate_daily_behavior

UTC = timezone.utc
WINDOWS_PER_DAY = 100
TODAY = datetime.now(TARGET_TZ).date()
TARGET = TODAY - timedelta(days=1)


@pytest.fixture
def scenario(binary_case, monkeypatch):
    """Build an animal whose baseline days and target day have given Active counts."""
    db = binary_case.db
    # New data has a reception time: coverage must be configured for it to be evaluated.
    monkeypatch.setattr(settings, "ANOMALY_MIN_COVERAGE_SECONDS", 60.0)

    def build(baseline_active, target_active, target=TARGET):
        device = Device(id=f"ANO-{uuid4().hex[:8]}", farm_id=binary_case.farm.id, status="active")
        db.add(device)
        db.flush()
        animal = Animal(farm_id=binary_case.farm.id, name="Scoring cow", status="active", assigned_device=device.id)
        db.add(animal)
        db.flush()
        days = [target - timedelta(days=k) for k in range(len(baseline_active), 0, -1)] + [target]
        for day, active in zip(days, list(baseline_active) + [target_active]):
            start = datetime.combine(day, time(8, 0), tzinfo=TARGET_TZ)
            for index in range(WINDOWS_PER_DAY):
                moment = (start + timedelta(seconds=20 * index)).astimezone(UTC)
                db.add(Telemetry(time=moment, animal_id=animal.id, device_id=device.id, received_at=moment,
                                 time_source="device_utc", protocol_version=2, behavior_eligible=True,
                                 activity=0.1, activity_state="lying", sample_rate=10, window_samples=150,
                                 battery_level=50, behavior_confidence=0.9,
                                 predicted_behavior="Active" if index < active else "Resting"))
        db.commit()
        for day in days:
            aggregate_daily_behavior(db, animal.id, day)
        return animal

    def evaluate(animal, target=TARGET):
        return ad.evaluate_animal_anomaly(db, animal.id, target)

    return build, evaluate, db


# ── 7.5 MAD == 0 ────────────────────────────────────────────────────────────

def test_a4a_twelve_identical_days_then_one_active_window_gives_no_alert(scenario):
    build, evaluate, _ = scenario
    assert evaluate(build([0] * 12, 1)) is None  # change 1 pt < 5 pts


def test_a4c_majority_identical_days_then_one_active_window_gives_no_alert(scenario):
    build, evaluate, _ = scenario
    assert evaluate(build([0] * 7 + [10, 15, 20, 25, 30], 1)) is None


def test_real_change_with_mad_zero_uses_mean_ad(scenario):
    build, evaluate, _ = scenario
    alert = evaluate(build([0] * 7 + [1, 2, 3, 4, 5], 30))
    assert alert is not None and alert.type == "activity_deviation_high"
    meta = alert.alert_metadata
    assert meta["z_scale"] == "MeanAD" and meta["baseline_mad"] == 0
    assert meta["baseline_mean_ad"] == pytest.approx(15 / 12, abs=1e-4)
    assert meta["z_score"] == pytest.approx(30 / (ad.MEAN_AD_CONSISTENCY * 15 / 12), abs=0.01)
    assert "reason" not in meta


@pytest.mark.parametrize("target_active,expect_alert", [(24, False), (25, True)])
def test_identical_baseline_alerts_only_from_five_points(scenario, target_active, expect_alert):
    build, evaluate, _ = scenario
    alert = evaluate(build([20] * 12, target_active))  # change 4.0 pts, then exactly 5.0 pts
    if not expect_alert:
        assert alert is None
        return
    assert alert.severity == "warning"
    meta = alert.alert_metadata
    assert meta["z_scale"] == "none" and meta["z_score"] is None
    assert meta["reason"] == "baseline_without_variation"
    assert meta["baseline_mad"] == 0 and meta["baseline_mean_ad"] == 0


# ── 7.6 Threshold 3.5 on a normal baseline (median 50, MAD 5) ───────────────

NORMAL_BASELINE = [40, 42, 44, 46, 48, 50, 50, 52, 54, 56, 58, 60]


@pytest.mark.parametrize("target_active,z_value,expect_alert", [
    (74, 0.6745 * 24 / 5, False),  # |Z| = 3.24: alerted with the old 3.0 threshold
    (77, 0.6745 * 27 / 5, True),   # |Z| = 3.64: warning (below the 4.5 heuristic tier)
])
def test_threshold_is_3_5(scenario, target_active, z_value, expect_alert):
    build, evaluate, _ = scenario
    assert ad.score_deviation(float(target_active), [float(v) for v in NORMAL_BASELINE])[:2] == (
        pytest.approx(z_value), "MAD")
    alert = evaluate(build(NORMAL_BASELINE, target_active))
    if not expect_alert:
        assert alert is None
        return
    assert alert.severity == "warning"
    assert alert.alert_metadata["z_scale"] == "MAD"
    assert alert.alert_metadata["z_score"] == pytest.approx(z_value, abs=0.01)


def test_critical_tier_stays_at_4_5(scenario):
    build, evaluate, _ = scenario
    alert = evaluate(build(NORMAL_BASELINE, 90))  # |Z| = 0.6745 * 40 / 5 = 5.40
    assert alert.severity == "critical" and alert.alert_metadata["z_score"] == pytest.approx(5.40, abs=0.01)


def test_compute_modified_z_score_needs_a_positive_mad():
    assert ad.compute_modified_z_score(10, 4, 2) == pytest.approx(0.6745 * 6 / 2)
    with pytest.raises(ValueError):
        ad.compute_modified_z_score(10, 4, 0)


# ── 7.7 Warm-up anchored to the evaluated date ──────────────────────────────

def test_date_40_days_back_with_12_days_of_prior_history_is_evaluated(scenario):
    build, evaluate, _ = scenario
    old_target = TODAY - timedelta(days=40)
    alert = evaluate(build(NORMAL_BASELINE, 90, target=old_target), target=old_target)
    assert alert is not None and alert.alert_metadata["target_date"] == old_target.isoformat()


def test_history_after_the_evaluated_date_does_not_count(scenario):
    build, evaluate, db = scenario
    # 12 days AFTER the evaluated date, none before it: the warm-up must refuse.
    animal = build(NORMAL_BASELINE, 90, target=TARGET)
    early = TARGET - timedelta(days=len(NORMAL_BASELINE) + 1)
    assert not ad.has_sufficient_history(db, animal.id, target_date=early)
    assert ad.has_sufficient_history(db, animal.id, target_date=TARGET)
    assert db.query(Alert).filter_by(animal_id=animal.id).count() == 0
