"""Step 2 core: label maps, windows, metrics, LOAO, results folder safety.

Synthetic data only: the Japanese Black CSVs are git-ignored and may be absent.
"""

import json

import numpy as np
import pandas as pd
import pytest

from ml import train_v2
from ml.step2 import evaluate, labels, run, windows


def test_active_resting_v1_is_exactly_the_m0_mapping():
    label_map = labels.load_label_map("active_resting_v1")
    assert label_map.maps["japanese_black"] == train_v2.BEHAVIOR_MAP
    assert list(label_map.classes) == train_v2.SIMPLIFIED_STATES
    assert set(label_map.excluded["japanese_black"]) == train_v2.EXCLUDED_LABELS


def test_label_map_rejects_unknown_class(tmp_path):
    path = tmp_path / "bad_v1.json"
    path.write_text(json.dumps({"name": "bad_v1", "classes": ["A", "B"],
                                "maps": {"d": {"x": "A", "y": "C"}}}), encoding="utf-8")
    with pytest.raises(ValueError, match="unknown classes"):
        labels.load_label_map(path)


def _df10(labels_per_segment, seed=0):
    """Synthetic 10 Hz table: one animal, one row per label, a segment per list."""
    rng = np.random.default_rng(seed)
    parts = []
    for segment_id, seg_labels in enumerate(labels_per_segment):
        n = len(seg_labels)
        parts.append(pd.DataFrame({
            "dataset": "japanese_black", "animal_id": "cow1", "day": "2020-06-12",
            "segment_id": segment_id, "t_ms": np.arange(n) * 100 + segment_id * 10**7,
            "ax": rng.normal(0, 0.1, n), "ay": rng.normal(0, 0.1, n), "az": rng.normal(-1, 0.1, n),
            "label_native": seg_labels,
        }))
    return pd.concat(parts, ignore_index=True)


def test_windows_purity_rule_and_segments():
    first = ["RES"] * 120 + ["MOV"] * 30      # purity 0.80 -> kept
    second = ["RES"] * 119 + ["MOV"] * 31     # purity 0.79 -> dropped
    short = ["MOV"] * 149                      # shorter than one window -> none
    df10 = _df10([first + second, short])
    w = windows.make_windows(df10, 150, 0.80)
    assert len(w) == 1
    assert w.loc[0, "label_native"] == "RES"
    assert w.loc[0, "purity"] == pytest.approx(0.80)
    v = df10["az"].to_numpy()[:150]
    assert w.loc[0, "accel_z_std"] == np.std(v)


def test_windows_equal_train_v2_windowing():
    rng = np.random.default_rng(1)
    seg = list(rng.choice(["RES", "MOV", "GRZ", "", "ETC"], size=40))
    df10 = _df10([[label for label in seg for _ in range(200)]] * 3)
    ours = windows.apply_label_map(windows.make_windows(df10, 150, 0.80),
                                   labels.load_label_map("active_resting_v1"))
    legacy = df10.rename(columns={"ax": "AccX", "ay": "AccY", "az": "AccZ", "label_native": "Label"})
    theirs = train_v2.apply_windowing(legacy)
    assert len(ours) == len(theirs) > 0
    assert (ours["label_native"].to_numpy() == theirs["label_raw"].to_numpy()).all()
    assert (ours["label"].to_numpy() == theirs["label_simplified"].to_numpy()).all()
    for col in windows.FEATURE_COLUMNS:
        assert (ours[col].to_numpy() == theirs[col].to_numpy()).all(), col


def test_classification_metrics_known_values():
    m = evaluate.classification_metrics(np.array([0, 0, 0, 1]), np.array([0, 0, 1, 1]), ["A", "B"])
    assert m["balanced_accuracy"] == pytest.approx((2 / 3 + 1) / 2)
    assert m["per_class"]["B"]["precision"] == pytest.approx(0.5)
    assert m["macro_f1"] == pytest.approx((0.8 + 2 / 3) / 2)
    assert m["confusion_matrix"] == [[2, 1], [0, 1]]


def test_classification_metrics_absent_class_is_na_not_zero():
    m = evaluate.classification_metrics(np.array([0, 0]), np.array([0, 1]), ["A", "B"])
    assert m["per_class"]["B"] == {"precision": None, "recall": None, "f1": None, "support": 0}
    assert m["macro_f1"] == pytest.approx(2 / 3)  # only class A counts


def _windows_table(n_animals=4, per_class=12, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for a in range(n_animals):
        for label, scale in (("Active", 0.5), ("Resting", 0.05)):
            for _ in range(per_class):
                row = {"dataset": "d", "animal_id": f"a{a}", "label": label}
                row.update({c: rng.normal(0, scale) for c in windows.FEATURE_COLUMNS})
                rows.append(row)
    return pd.DataFrame(rows)


def test_loao_holds_out_each_animal_and_is_deterministic():
    w = _windows_table()
    groups = w["dataset"] + "/" + w["animal_id"]
    forest = evaluate.ForestConfig(n_estimators=20)
    r1 = evaluate.cross_validate(w, groups, ["Active", "Resting"], windows.FEATURE_COLUMNS, forest, 42)
    r2 = evaluate.cross_validate(w, groups, ["Active", "Resting"], windows.FEATURE_COLUMNS, forest, 42)
    assert [f["test_group"] for f in r1["folds"]] == ["d/a0", "d/a1", "d/a2", "d/a3"]
    for f in r1["folds"]:
        assert f["n_test"] == 24 and f["n_train"] == 72
    assert r1["pooled"] == r2["pooled"]
    assert r1["across_folds"]["balanced_accuracy"]["n"] == 4


def test_fold_without_a_class_in_training_is_skipped():
    w = _windows_table(n_animals=3)
    w = w[~((w["animal_id"] != "a0") & (w["label"] == "Active"))]  # only a0 has Active
    groups = w["dataset"] + "/" + w["animal_id"]
    r = evaluate.cross_validate(w, groups, ["Active", "Resting"], windows.FEATURE_COLUMNS,
                                evaluate.ForestConfig(n_estimators=10), 42)
    assert [s["test_group"] for s in r["skipped"]] == ["d/a0"]


def test_run_refuses_existing_results_folder(tmp_path):
    (tmp_path / "already_there").mkdir()
    with pytest.raises(SystemExit, match="never overwritten"):
        run.main(["--name", "already_there", "--results-dir", str(tmp_path)])


@pytest.mark.parametrize("bad", ["../models/x", "Upper", "a", "v3 staged"])
def test_run_rejects_unsafe_names(tmp_path, bad):
    with pytest.raises(SystemExit, match="Invalid --name"):
        run.main(["--name", bad, "--results-dir", str(tmp_path)])
