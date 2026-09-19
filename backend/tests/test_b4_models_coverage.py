"""Model slot isolation and coverage safeguards, without training any artifact."""

from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace
from datetime import datetime, timedelta, timezone
import pickle
import numpy as np
import pytest
from sklearn.preprocessing import LabelEncoder

from app.services import ml_inference
from app.services.behavior_coverage import covered_seconds, insufficient_coverage_days
from app.core.config import settings
from app.core.binary_protocol import FEATURE_NAMES
from app.core.timezone import TARGET_TZ, utc_now
from app.models.telemetry import Telemetry


def fake_artifact(active):
    return {"features": list(FEATURE_NAMES), "label_encoder": LabelEncoder().fit(["Active", "Resting"]),
            "model": SimpleNamespace(predict_proba=lambda _: np.array([[active, 1 - active]]))}


def test_model_selection_does_not_mutate_a_current_model(monkeypatch):
    old = fake_artifact(.9)
    new = fake_artifact(.1)
    monkeypatch.setattr(ml_inference, "_artifact", old)
    monkeypatch.setattr(ml_inference, "_profiles", {(10, 150): new})
    features = {name: 0.0 for name in FEATURE_NAMES}
    def run(samples):
        return ml_inference.predict_with_confidence({**features, "sample_rate": 10, "window_samples": samples})[0]
    with ThreadPoolExecutor(max_workers=4) as executor:
        assert list(executor.map(run, [50, 150] * 20)) == ["Active", "Resting"] * 20
    assert ml_inference._artifact is old and ml_inference._profiles[(10, 150)] is new
    assert ml_inference.predict_with_confidence(features)[0] == "Active"
    assert ml_inference.predict_with_confidence({**features, "sample_rate": 10}) == (None, None)


def test_invalid_artifacts_are_unavailable_without_crashing_startup(tmp_path):
    path = tmp_path / "invalid.pkl"
    path.write_bytes(b"not-a-pickle")
    assert ml_inference._load_artifact(path, (10, 150)) is None
    path.write_bytes(pickle.dumps({"target_freq": 10, "window_samples": 50}))
    assert ml_inference._load_artifact(path, (10, 150)) is None


@pytest.mark.parametrize("invalid", ["classes", "feature_count", "missing_metrics", "nonfinite_metrics"])
def test_loader_rejects_inconsistent_model_metadata(tmp_path, monkeypatch, invalid):
    artifact = fake_artifact(.9)
    artifact.update(target_freq=10, window_samples=150, loao_metrics={
        "mean_per_fold_accuracy": .9, "std_per_fold_accuracy": .02,
        "ci_95_low": .85, "ci_95_high": .95,
    })
    artifact["model"].classes_ = [0, 1]
    artifact["model"].n_features_in_ = len(FEATURE_NAMES)
    if invalid == "classes":
        artifact["model"].classes_ = [1, 0]
    elif invalid == "feature_count":
        artifact["model"].n_features_in_ = 11
    elif invalid == "missing_metrics":
        artifact["loao_metrics"].pop("ci_95_high")
    else:
        artifact["loao_metrics"]["mean_per_fold_accuracy"] = float("nan")
    path = tmp_path / "metadata.pkl"
    path.write_bytes(b"trusted-local-test-double")
    monkeypatch.setattr(ml_inference.pickle, "loads", lambda _: artifact)
    assert ml_inference._load_artifact(path, (10, 150)) is None


def test_coverage_does_not_double_count_overlap_or_fill_gaps():
    start = datetime(2026, 9, 13, tzinfo=timezone.utc)
    assert covered_seconds([(start, start + timedelta(seconds=15)),
                            (start + timedelta(seconds=10), start + timedelta(seconds=25)),
                            (start + timedelta(seconds=40), start + timedelta(seconds=50))]) == 35
    assert covered_seconds([]) == 0


def test_new_days_require_an_explicit_coverage_threshold(binary_case, monkeypatch):
    case = binary_case
    stamp = utc_now().astimezone(TARGET_TZ).replace(hour=12, minute=0, second=0, microsecond=0)
    case.db.add(Telemetry(animal_id=case.animal.id, device_id=case.device.id,
                          time=stamp, received_at=utc_now(), sample_rate=10, window_samples=150,
                          behavior_eligible=True, predicted_behavior="Active"))
    case.db.commit()
    monkeypatch.setattr(settings, "ANOMALY_MIN_COVERAGE_SECONDS", None)
    assert insufficient_coverage_days(case.db, case.animal.id, stamp.date(), stamp.date()) == {stamp.date()}
    monkeypatch.setattr(settings, "ANOMALY_MIN_COVERAGE_SECONDS", 15)
    assert insufficient_coverage_days(case.db, case.animal.id, stamp.date(), stamp.date()) == set()
    monkeypatch.setattr(settings, "ANOMALY_MIN_COVERAGE_SECONDS", 16)
    assert insufficient_coverage_days(case.db, case.animal.id, stamp.date(), stamp.date()) == {stamp.date()}
