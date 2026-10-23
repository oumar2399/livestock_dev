"""Step 2: Ito (Japanese Black) through the shared pipeline.

Small synthetic cow*.csv files and a synthetic registry in tmp_path only; the
real Ito CSVs are never read.
"""

import json

import numpy as np
import pandas as pd
import pytest

from ml.step2 import datasets, harmonise, ito_shared, preprocess, segments, summarise_ito
from ml.step2.datasets import sha256_file
from ml.step2.external_datasets import _outcome

T0 = int(pd.Timestamp("2020-06-12 02:22:00", tz="UTC").timestamp() * 1000)  # 11:22 JST

DECIDED = {  # the mapping decided for Ito (same rules as Versluijs and Morales-Vargas)
    "MOV": "moving", "GRZ": "grazing", "RES": "resting", "RUS": "resting", "REL": "resting",
    "DRN": "drinking", "SLT": "excluded:salt_licking", "FES": "excluded:feeding_stanchion",
    "LCK": "excluded:body_care", "URI": "excluded:excretion", "ATT": "excluded:social_interaction",
    "ESC": "excluded:social_interaction", "BMN": "excluded:social_interaction",
    "ETC": "excluded:other", "": "excluded:unlabeled",
}


def _cow(data_dir, name, bouts, drop=(), out_of_range=(), seed=0):
    """25 Hz cow CSV: contiguous bouts [(label, seconds)], raw samples whose
    offset (ms) is in a [start, stop) range of `drop` removed."""
    labels = [label for label, seconds in bouts for _ in range(seconds * 25)]
    offset = np.arange(len(labels)) * 40
    rng = np.random.default_rng(seed)
    df = pd.DataFrame({
        "TimeStamp_UNIX": T0 + offset,
        "AccX": rng.normal(0, 0.05, len(labels)), "AccY": rng.normal(0, 0.05, len(labels)),
        "AccZ": rng.normal(-1, 0.05, len(labels)), "Label": labels,
    })
    for i in out_of_range:
        df.loc[i, "AccX"] = 7.0  # outside train_v2.ACC_BOUNDS: dropped by the loader
    keep = np.ones(len(df), dtype=bool)
    for start, stop in drop:
        keep &= ~((offset >= start) & (offset < stop))
    data_dir.mkdir(parents=True, exist_ok=True)
    df[keep].to_csv(data_dir / f"{name}.csv", index=False)


def _registry(tmp_path, data_dir, only=None, bad=None):
    rows = ["| File | Bytes | SHA-256 |", "|---|---|---|"]
    for f in sorted(data_dir.glob("cow*.csv")):
        if only is None or f.name in only:
            digest = "0" * 64 if f.name == bad else sha256_file(f)
            rows.append(f"| {f.name} | {f.stat().st_size} | `{digest}` |")
    path = tmp_path / "model_registry.md"
    path.write_text("## Dataset facts\n\n" + "\n".join(rows) + "\n", encoding="utf-8")
    return path


def _boundary_data(tmp_path):
    """cow1: one missed tick (~10.2 s) and one filter restart (raw gap 560 ms at 25 s);
    cow2: one filter restart after a 1.56 s raw gap (> 1 s: the shared rule splits too)."""
    data_dir = tmp_path / "ito"
    _cow(data_dir, "cow1", [("RES", 40)], drop=[(10160, 10280), (25000, 25520)])
    _cow(data_dir, "cow2", [("RES", 20)], drop=[(8000, 9500)], seed=1)
    return data_dir, _registry(tmp_path, data_dir)


def test_mapping_table_is_the_decided_one_and_every_label_maps(tmp_path):
    assert ito_shared.ITO_LABELS == DECIDED
    data_dir = tmp_path / "ito"
    _cow(data_dir, "cow1", [(label, 2) for label in DECIDED])
    s = ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir)).samples
    got = s.groupby("label_native")[["base_class", "exclusion_reason"]].first()
    assert set(got.index) == set(DECIDED)
    for label, outcome in DECIDED.items():
        assert tuple(got.loc[label]) == _outcome(outcome)


@pytest.mark.parametrize("label", ["XYZ", "BLN"])
def test_label_not_in_the_table_stops_the_load(tmp_path, label):
    data_dir = tmp_path / "ito"
    _cow(data_dir, "cow1", [("RES", 2), (label, 2)])
    with pytest.raises(ValueError, match="not in the mapping table"):
        ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir))


def test_conversion_relative_time_day_axes_and_posture(tmp_path):
    data_dir = tmp_path / "ito"
    _cow(data_dir, "cow1", [("RES", 30)])
    _cow(data_dir, "cow2", [("MOV", 20)], seed=1)
    s = ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir)).samples
    assert "t_ms" not in s.columns and s["t_rel_ms"].dtype == np.int64
    assert s.groupby("animal_id")["t_rel_ms"].min().to_dict() == {"cow1": 0, "cow2": 0}
    assert (s.groupby("animal_id")["t_rel_ms"].diff().dropna() == 100).all()
    assert s["day"].unique().tolist() == ["2020-06-12"] and (s["posture"] == "").all()

    raw, _ = datasets.load_japanese_black(data_dir)
    df10 = preprocess.device_lp_point_10hz(raw, "Asia/Tokyo", 25, cutoff_hz=5.1, order=1)
    df10 = df10.sort_values(["animal_id", "t_ms"], kind="stable")
    for col in ["ax", "ay", "az"]:
        assert np.array_equal(s[col].to_numpy(), df10[col].to_numpy())


def test_device_preprocessing_parameters(tmp_path, monkeypatch):
    calls, original = [], preprocess.device_lp_point_10hz

    def spy(raw, timezone, native_hz, cutoff_hz=None, order=None):
        calls.append((timezone, native_hz, cutoff_hz, order))
        return original(raw, timezone, native_hz, cutoff_hz, order)

    monkeypatch.setattr(preprocess, "device_lp_point_10hz", spy)
    data_dir = tmp_path / "ito"
    _cow(data_dir, "cow1", [("RES", 5)])
    loaded = ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir))
    assert calls == [("Asia/Tokyo", 25, 5.1, 1)]
    assert loaded.preprocess["arguments"] == {"timezone": "Asia/Tokyo", "native_hz": 25, "cutoff_hz": 5.1, "order": 1}


def test_registry_hashes(tmp_path):
    data_dir = tmp_path / "ito"
    _cow(data_dir, "cow1", [("RES", 2)])
    _cow(data_dir, "cow2", [("RES", 2)], seed=1)
    assert ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir)).hash_check["status"].startswith("all files match")
    with pytest.raises(ValueError, match="SHA-256 or size mismatch"):
        ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir, bad="cow2.csv"))
    with pytest.raises(ValueError, match="differ from"):
        ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir, only={"cow1.csv"}))
    status = ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir, only=set())).hash_check["status"]
    assert status.startswith("no hashes recorded")


def test_row_accounting_includes_the_loader_cleaning(tmp_path):
    data_dir = tmp_path / "ito"
    _cow(data_dir, "cow1", [("RES", 10), ("ETC", 4), ("", 4)], out_of_range=[30])
    loaded = ito_shared.load_ito(data_dir, _registry(tmp_path, data_dir))
    items = {r["item"]: r["rows"] for r in loaded.accounting}
    assert (items["raw_rows"], items["dropped_by_loader_cleaning"], items["rows_25hz_loaded"]) == (450, 1, 449)
    assert items["samples_10hz"] == len(loaded.samples)
    assert {"mapped:resting", "excluded:other", "excluded:unlabeled"} <= set(items)
    counted = sum(n for k, n in items.items() if k.startswith(("mapped:", "excluded:")))
    assert counted == items["samples_10hz"]


def test_device_block_boundaries_missed_ticks_and_filter_restarts(tmp_path):
    loaded = ito_shared.load_ito(*_boundary_data(tmp_path))
    assert sorted(loaded.boundaries["kind"]) == ["filter_restart", "filter_restart", "missed_tick"]
    assert not {"t_ms", "t_start_ms"} & set(loaded.boundaries.columns)

    samples = harmonise.harmonise(loaded.samples)[0]
    win = segments.make_windows(samples)
    assert win["n_samples"].tolist() == [149, 145]  # cow1: missed tick in window 0, restart in window 1
    report = ito_shared.boundary_report(samples, loaded.boundaries, win).set_index("kind")
    cols = ["boundaries", "step_le_1000ms", "inside_shared_segment", "valid_windows_containing"]
    assert report.loc["missed_tick", cols].tolist() == [1, 1, 1, 1]
    assert report.loc["filter_restart", cols].tolist() == [2, 1, 1, 1]
    assert report.loc["all", cols].tolist() == [3, 2, 2, 2]


def test_summary_writes_only_aggregates_and_refuses_an_existing_folder(tmp_path):
    data_dir, registry = _boundary_data(tmp_path)
    results = tmp_path / "results"
    args = ["--name", "syn_ito", "--results-dir", str(results), "--data-dir", str(data_dir),
            "--registry", str(registry)]
    assert summarise_ito.main(args) == 0
    folder = results / "syn_ito"
    assert {p.name for p in folder.iterdir()} == {
        "config.json", "run.log", "row_accounting.csv", "windows_per_class.csv",
        "windows_per_class_per_animal.csv", "gravity_resting.csv", "device_block_boundaries.csv"}

    counts = pd.read_csv(folder / "windows_per_class.csv", keep_default_na=False)
    by = counts.set_index(["dataset", "scheme", "class"])["windows_ge142"].to_dict()
    assert by == {("japanese_black", s, c): 2 for s, c in [("base", "resting"), ("2-class", "resting"), ("3-class", "resting")]}
    gravity = pd.read_csv(folder / "gravity_resting.csv", keep_default_na=False)
    assert set(gravity["label_native"]) == {"RES"} and set(gravity["quantise"]) == {True, False}

    for name in ["row_accounting.csv", "windows_per_class.csv", "windows_per_class_per_animal.csv",
                 "gravity_resting.csv", "device_block_boundaries.csv"]:
        columns = set(pd.read_csv(folder / name).columns)
        assert not columns & {"t_rel_ms", "t_ms", "ax", "ay", "az", "accel_x_mean", "t_rel_before_ms"}

    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    assert config["preprocess"]["arguments"] == {"timezone": "Asia/Tokyo", "native_hz": 25, "cutoff_hz": 5.1, "order": 1}
    assert {"step2/windows.py", "step2/preprocess.py"} <= set(config["code_sha256"])
    assert config["data"]["japanese_black"]["hash_check"]["status"].startswith("all files match")

    with pytest.raises(SystemExit, match="already exists"):
        summarise_ito.main(args)
