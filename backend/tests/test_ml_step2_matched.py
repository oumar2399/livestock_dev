"""Step 2 follow-up: active_inactive_v2, predictions.csv, per-native-label
diagnosis, matched-window comparison (binmean_matched + compare)."""

import json

import numpy as np
import pandas as pd
import pytest

from ml.step2 import compare, datasets, evaluate, labels, preprocess, run, windows


def test_active_inactive_v2_excludes_pen_only_behaviours_and_being_mounted():
    v1 = labels.load_label_map("active_inactive_v1")
    v2 = labels.load_label_map("active_inactive_v2")
    jb1, jb2 = v1.maps["japanese_black"], v2.maps["japanese_black"]
    assert {"BMN", "SLT", "FES"} <= set(v2.excluded["japanese_black"])
    assert jb2["DRN"] == "Active" and jb2["GRZ"] == "Active"
    # every native code is still either mapped or excluded, and the kept ones keep their v1 class
    all_codes = set(jb1) | set(v1.excluded["japanese_black"])
    assert set(jb2) | set(v2.excluded["japanese_black"]) == all_codes
    assert all(jb1[code] == cls for code, cls in jb2.items())
    assert {"BMN", "SLT", "FES"} <= set(v2.reasons)


def _windows_table(n_animals=3, per_class=10, seed=0):
    rng = np.random.default_rng(seed)
    rows = []
    for a in range(n_animals):
        for label, native, scale in (("Active", "MOV", 0.5), ("Resting", "RES", 0.05)):
            for _ in range(per_class):
                row = {"dataset": "d", "animal_id": f"a{a}", "label": label, "label_native": native}
                row.update({c: rng.normal(0, scale) for c in windows.FEATURE_COLUMNS})
                rows.append(row)
    return pd.DataFrame(rows)


def test_predictions_are_aligned_with_windows_and_match_fold_metrics():
    w = _windows_table()
    groups = w["dataset"] + "/" + w["animal_id"]
    r = evaluate.cross_validate(w, groups, ["Active", "Resting"], windows.FEATURE_COLUMNS,
                                evaluate.ForestConfig(n_estimators=10), 42)
    assert len(r["predicted"]) == len(w) and all(p in ("Active", "Resting") for p in r["predicted"])
    for fold in r["folds"]:
        m = (groups == fold["test_group"]).to_numpy()
        correct = (r["predicted"][m] == w["label"].to_numpy()[m]).sum()
        assert correct == fold["confusion_matrix"][0][0] + fold["confusion_matrix"][1][1]


def test_native_label_breakdown_counts():
    w = pd.DataFrame({"label": ["A", "A", "A", "B"], "label_native": ["SLT", "SLT", "MOV", "RES"]})
    groups = pd.Series(["g1", "g2", "g2", "g1"])
    predicted = np.array(["B", "A", "A", None], dtype=object)   # last window: fold skipped
    rows = {(r["class"], r["label_native"]): r for r in evaluate.native_label_breakdown(w, groups, predicted)}
    assert rows[("A", "SLT")]["correct"] == 1 and rows[("A", "SLT")]["n"] == 2
    assert rows[("A", "SLT")]["by_group"] == {"g1": [0, 1], "g2": [1, 1]}
    assert ("B", "RES") not in rows


def test_binmean_on_device_windows_keeps_windows_and_bins_around_each_tick():
    raw, _ = datasets.make_synthetic("synthetic_a", 1, n_animals=1, n_days=1, bouts_per_day=4)
    plan = windows.make_windows(preprocess.device_lp_point_10hz(raw, "UTC", 25), 150, 0.8)
    matched = preprocess.binmean_on_device_windows(plan, raw, 150)
    keys = ["dataset", "animal_id", "day", "segment_id", "t_start_ms", "label_native", "purity"]
    assert matched[keys].equals(plan[keys])
    # reference computation for the first window: mean of raw samples within +-50 ms of each tick
    t, x = raw["t_ms"].to_numpy(), raw["ax"].to_numpy()
    ticks = plan.loc[0, "t_start_ms"] + 100 * np.arange(150)
    bins = np.array([x[(t >= k - 50) & (t < k + 50)].mean() for k in ticks])
    assert matched.loc[0, "accel_x_mean"] == pytest.approx(bins.mean())
    assert matched.loc[0, "accel_x_std"] == pytest.approx(bins.std())
    assert matched.loc[0, "accel_x_max"] == pytest.approx(bins.max())


def _label_map(tmp_path):
    mapping = {"WALK": "Active", "GRAZE": "Active", "REST": "Inactive"}
    path = tmp_path / "synthetic_test_v1.json"
    path.write_text(json.dumps({"name": "synthetic_test_v1", "classes": ["Active", "Inactive"],
                                "maps": {"synthetic_a": mapping}, "excluded": {"synthetic_a": [""]}}),
                    encoding="utf-8")
    return str(path)


def _run(tmp_path, name, preprocessing, *extra):
    # binmean (M0's resample) is avoided here: on the 2-day synthetic data it fills
    # every 100 ms bin between the days and takes minutes.
    assert run.main(["--name", name, "--datasets", "synthetic_a", "--label-map", _label_map(tmp_path),
                     "--preprocess", preprocessing, "--trees", "10", "--seeds", "42", "43",
                     "--results-dir", str(tmp_path / "results"), *extra]) == 0
    return tmp_path / "results" / name


def test_runs_save_predictions_and_native_breakdown(tmp_path):
    folder = _run(tmp_path, "syn_device", "device_lp_point")
    pred = pd.read_csv(folder / "predictions.csv", keep_default_na=False)
    assert {"pred_seed42", "pred_seed43", "label_native", "test_group"} <= set(pred.columns)
    metrics = json.loads((folder / "metrics.json").read_text(encoding="utf-8"))
    assert {r["label_native"] for r in metrics["native_label_breakdown"]} == {"WALK", "GRAZE", "REST"}


def test_matched_comparison_end_to_end(tmp_path):
    _run(tmp_path, "syn_device", "device_lp_point")
    _run(tmp_path, "syn_binmatched", "binmean_matched")
    results = tmp_path / "results"
    assert compare.main(["--name", "syn_cmp", "--a", "syn_binmatched", "--b", "syn_device",
                         "--results-dir", str(results)]) == 0
    out = json.loads((results / "syn_cmp" / "comparison.json").read_text(encoding="utf-8"))
    assert set(out["delta_mean_balanced_accuracy_b_minus_a"]["per_seed"]) == {"42", "43"}
    assert out["n_windows"] == len(pd.read_csv(results / "syn_device" / "predictions.csv"))
    agreement = pd.read_csv(results / "syn_cmp" / "agreement_by_group.csv")
    assert (agreement["correct_a"] - agreement["only_a"] == agreement["correct_b"] - agreement["only_b"]).all()


def test_compare_refuses_runs_with_different_windows(tmp_path):
    _run(tmp_path, "syn_device", "device_lp_point")
    _run(tmp_path, "syn_short", "binmean_matched", "--window-seconds", "10")   # other windows
    with pytest.raises(SystemExit, match="Not a matched comparison"):
        compare.main(["--name", "syn_bad", "--a", "syn_short", "--b", "syn_device",
                      "--results-dir", str(tmp_path / "results")])
    assert not (tmp_path / "results" / "syn_bad").exists()
