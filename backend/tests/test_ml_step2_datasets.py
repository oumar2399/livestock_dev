"""Step 2, Step C: canonical datasets, validation schemes, device filter boundary.

Runs the whole CLI on two small synthetic datasets (no real data needed).
"""

import json

import numpy as np
import pandas as pd
import pytest

from ml.step2 import datasets, run


def _label_map(tmp_path):
    mapping = {"WALK": "Active", "GRAZE": "Active", "REST": "Inactive"}
    path = tmp_path / "synthetic_test_v1.json"
    path.write_text(json.dumps({
        "name": "synthetic_test_v1", "classes": ["Active", "Inactive"],
        "maps": {"synthetic_a": mapping, "synthetic_b": mapping},
        "excluded": {"synthetic_a": [""], "synthetic_b": [""]},
    }), encoding="utf-8")
    return str(path)


def _run(tmp_path, name, *extra):
    results = tmp_path / "results"
    code = run.main(["--name", name, "--label-map", _label_map(tmp_path), "--trees", "20",
                     "--preprocess", "device_lp_point", "--results-dir", str(results), *extra])
    assert code == 0
    folder = results / name
    return (json.loads((folder / "metrics.json").read_text(encoding="utf-8")),
            json.loads((folder / "config.json").read_text(encoding="utf-8")))


def test_synthetic_datasets_are_canonical():
    raw, manifest, specs = datasets.load(["synthetic_a", "synthetic_b"])
    assert list(raw.columns) == datasets.CANONICAL_COLUMNS
    assert raw.groupby("dataset")["animal_id"].nunique().to_dict() == {"synthetic_a": 3, "synthetic_b": 3}
    assert raw.groupby("dataset")["day"].nunique().to_dict() == {"synthetic_a": 2, "synthetic_b": 2}
    assert set(specs) == {"synthetic_a", "synthetic_b"} and len(manifest) == 2


def test_validate_canonical_rejects_bad_tables():
    raw, _ = datasets.make_synthetic("x", 0, n_animals=1, n_days=1, bouts_per_day=1)
    with pytest.raises(ValueError, match="columns"):
        datasets.validate_canonical(raw.drop(columns="day"))
    with pytest.raises(ValueError, match="int64"):
        datasets.validate_canonical(raw.assign(t_ms=raw["t_ms"].astype(float)))
    with pytest.raises(ValueError, match="strings"):
        datasets.validate_canonical(raw.assign(label_native=np.nan))


def test_device_data_across_the_filter_change_is_refused():
    boundary = int(datasets.DEVICE_FILTER_BOUNDARY.timestamp() * 1000)
    assert boundary == int(pd.Timestamp("2026-10-05T14:30:00Z").timestamp() * 1000)  # 23:30 JST
    assert datasets.filter_regime(pd.Series([boundary - 1])) == "unfiltered (A_DLPF_CFG=0)"
    assert datasets.filter_regime(pd.Series([boundary])) == "filtered (A_DLPF_CFG=6)"
    with pytest.raises(ValueError, match="spans 2026-10-05 23:30 JST"):
        datasets.filter_regime(pd.Series([boundary - 1, boundary]))


def test_leave_one_dataset_out(tmp_path):
    metrics, config = _run(tmp_path, "syn_lodo", "--datasets", "synthetic_a", "synthetic_b",
                           "--scheme", "lodo")
    folds = {f["test_group"]: f for f in metrics["folds"]}
    assert set(folds) == {"synthetic_a", "synthetic_b"}
    # each fold trains on exactly the other dataset's windows
    assert folds["synthetic_a"]["n_train"] == folds["synthetic_b"]["n_test"]
    assert folds["synthetic_b"]["n_train"] == folds["synthetic_a"]["n_test"]
    assert config["validation"]["scheme"] == "lodo"
    assert set(config["preprocess"]) == {"synthetic_a", "synthetic_b"}


def test_leave_one_day_out(tmp_path):
    metrics, config = _run(tmp_path, "syn_loday", "--datasets", "synthetic_a", "--scheme", "loday")
    assert [f["test_group"] for f in metrics["folds"]] == ["synthetic_a/2026-01-01", "synthetic_a/2026-01-02"]
    assert config["data"]["recording_days"] == {"synthetic_a": ["2026-01-01", "2026-01-02"]}


def test_leave_one_animal_out_across_two_datasets(tmp_path):
    metrics, _ = _run(tmp_path, "syn_loao", "--datasets", "synthetic_a", "synthetic_b")
    assert len(metrics["folds"]) == 6
    assert metrics["folds"][0]["test_group"] == "synthetic_a/s1"


def test_lodo_with_one_dataset_is_refused_and_leaves_nothing(tmp_path):
    with pytest.raises(SystemExit, match="at least 2 datasets"):
        _run(tmp_path, "syn_bad", "--datasets", "synthetic_a", "--scheme", "lodo")
    assert not any((tmp_path / "results").iterdir())


def test_loday_with_a_single_day_is_refused(tmp_path, monkeypatch):
    one_day = datasets.DatasetSpec("synthetic_a", 25, "UTC",
                                   lambda: datasets.make_synthetic("synthetic_a", 1, n_days=1), "1 day")
    monkeypatch.setitem(datasets.DATASETS, "synthetic_a", one_day)
    with pytest.raises(SystemExit, match="single recording day"):
        _run(tmp_path, "syn_one_day", "--datasets", "synthetic_a", "--scheme", "loday")
    assert not any((tmp_path / "results").iterdir())
