"""Step 2: Versluijs and Morales-Vargas loaders and the summary command.

Small synthetic files in tmp_path only; the real datasets are never read.
"""

import json

import numpy as np
import pandas as pd
import pytest

from ml.step2 import external_datasets as ext
from ml.step2 import harmonise, segments, summarise_external
from ml.step2.datasets import sha256_file

S, E, B, I, L, T, A, P = ext.VERSLUIJS_CATEGORIES
GRAZE, CHEW = "Feeding/Grazing_Grazing head low", "Feeding/Grazing_Chewing head high"
V_HEADER = ["serial", *ext.VERSLUIJS_CATEGORIES, "date", "date_id", "start_time", "xcal", "zcal", "ycal", "end_time"]


def _hash_file(tmp_path, root, files):
    path = tmp_path / f"{root.name}_sha256.txt"
    path.write_text("".join(f"{sha256_file(f)} *{f.relative_to(root.parent).as_posix()}\n" for f in files),
                    encoding="utf-8")
    return path


def _v_time(i, date="2021-06-22", start="10:00:00"):
    t = pd.Timestamp(f"{date} {start}") + pd.Timedelta(microseconds=100_000 * i + 100)
    return t.strftime("%Y-%m-%dT%H:%M:%S.%fZ")


def _v_row(serial, start_time, cats=None, date="2021-06-22", x=0.0, y=0.0, z=1.0):
    cats = cats or {}
    values = {"serial": str(serial), **{c: cats.get(c, "") for c in ext.VERSLUIJS_CATEGORIES},
              "date": date, "date_id": f"{date}_{serial}", "start_time": start_time,
              "xcal": f"{x}", "zcal": f"{z}", "ycal": f"{y}", "end_time": start_time}
    return ",".join(values[c] for c in V_HEADER)


def _versluijs(tmp_path, lines, name=ext.VERSLUIJS_FILE):
    root = tmp_path / "versluijs"
    root.mkdir(parents=True)
    path = root / name
    path.write_text("\n".join([",".join(V_HEADER), *lines]) + "\n", encoding="utf-8")
    hashes = tmp_path / "versluijs_sha256.txt"
    hashes.write_text(f"{sha256_file(path)} *versluijs/{ext.VERSLUIJS_FILE}\n", encoding="utf-8")
    return root, hashes


# ── Versluijs ─────────────────────────────────────────────────────────────────

CASES = [  # (categories, base class, exclusion reason)
    ({L: "Walking"}, "moving", ""),
    ({L: "Running"}, "moving", ""),
    ({L: "Trotting", P: "Standing"}, "moving", ""),
    ({I: GRAZE}, "grazing", ""),
    ({I: GRAZE, P: "Standing"}, "grazing", ""),
    ({I: "Ruminating"}, "resting", ""),
    ({I: "Ruminating", P: "Laying"}, "resting", ""),
    ({I: "Ruminating", P: "Standing"}, "resting", ""),
    ({I: "Drinking"}, "drinking", ""),
    ({I: "Drinking", P: "Standing"}, "drinking", ""),
    ({P: "Laying"}, "resting", ""),
    ({P: "Standing"}, "resting", ""),
    ({I: CHEW}, "", "chewing_head_high"),
    ({S: "Allogrooming", P: "Laying"}, "", "social_interaction"),
    ({E: "Urinating", P: "Standing"}, "", "excretion"),
    ({B: "Self-grooming"}, "", "body_care"),
    ({A: "Vigilance", P: "Standing"}, "", "alert"),
    ({T: "Getting up"}, "", "posture_transition"),
    ({S: "Butting", L: "Walking"}, "", "social_interaction"),  # exclusion before conflict
    ({I: GRAZE, L: "Walking"}, "", "conflict"),
    ({I: "Drinking", L: "Walking"}, "", "conflict"),
    ({I: "Ruminating", L: "Walking"}, "", "conflict"),
    ({L: "Walking", P: "Laying"}, "", "posture_conflict"),
    ({I: GRAZE, P: "Laying"}, "", "posture_conflict"),
    ({I: "Drinking", P: "Laying"}, "", "posture_conflict"),
    ({}, "", "unlabeled"),
]


def test_versluijs_mapping_rules(tmp_path):
    lines = [_v_row(1000 + i, _v_time(0), cats) for i, (cats, _, _) in enumerate(CASES)]
    loaded = ext.load_versluijs(*_versluijs(tmp_path, lines))
    s = loaded.samples.set_index("animal_id")
    for i, (cats, base, reason) in enumerate(CASES):
        row = s.loc[str(1000 + i)]
        native = "|".join(f"{c}={cats[c]}" for c in ext.VERSLUIJS_CATEGORIES if c in cats)
        assert (row["base_class"], row["exclusion_reason"]) == (base, reason), cats
        assert row["label_native"] == native
        assert row["posture"] == cats.get(P, "")  # a missing Posture stays missing

    items = {r["item"]: r["rows"] for r in loaded.accounting}
    assert items["rows_read"] == len(CASES)
    assert items["excluded:conflict"] == 3 and items["excluded:posture_conflict"] == 3
    assert items["mapped:resting"] == 5 and items["excluded:unlabeled"] == 1
    assert sum(n for k, n in items.items() if k != "rows_read") == len(CASES)


def test_versluijs_unknown_value_stops_the_load(tmp_path):
    with pytest.raises(ValueError, match="Galloping"):
        ext.load_versluijs(*_versluijs(tmp_path, [_v_row(1, _v_time(0), {L: "Galloping"})]))


def test_versluijs_axes_by_name(tmp_path):
    loaded = ext.load_versluijs(*_versluijs(tmp_path, [_v_row(1, _v_time(0), {P: "Laying"}, x=0.016, y=0.032, z=0.048)]))
    row = loaded.samples.iloc[0]
    assert (row["ax"], row["ay"], row["az"]) == (0.016, 0.032, 0.048)


def test_versluijs_relative_time_and_day_as_given(tmp_path):
    # crosses midnight in the time text; the date column says 2021-06-22 for both rows
    lines = [_v_row(1, "2021-06-22T23:59:59.900100Z", {P: "Laying"}),
             _v_row(1, "2021-06-23T00:00:00.000100Z", {P: "Laying"}),
             _v_row(2, _v_time(5), {P: "Laying"})]
    s = ext.load_versluijs(*_versluijs(tmp_path, lines)).samples.sort_values(["animal_id", "t_rel_ms"])
    assert s["day"].tolist() == ["2021-06-22"] * 3
    assert s["t_rel_ms"].tolist() == [0, 100, 0] and s["t_rel_ms"].dtype == np.int64
    assert list(s.columns) == ext.OUTPUT_COLUMNS
    assert not {"t_ms", "start_time", "end_time", "date"} & set(s.columns)


def test_versluijs_exact_file_name_and_hash(tmp_path):
    with pytest.raises(FileNotFoundError, match="exactly"):
        ext.load_versluijs(*_versluijs(tmp_path / "a", [_v_row(1, _v_time(0))], name="Annotated_acc_data.txt"))
    root, hashes = _versluijs(tmp_path / "b", [_v_row(1, _v_time(0))])
    hashes.write_text(f"{'0' * 64} *versluijs/{ext.VERSLUIJS_FILE}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ext.load_versluijs(root, hashes)


# ── Morales-Vargas ────────────────────────────────────────────────────────────

def _m_event(root, folder, event, label, cow, start, n, acc=(9.80665, 0.0, -9.80665), name_time=None):
    times = pd.Timestamp(start) + pd.to_timedelta(np.arange(n) * 100, unit="ms")
    stamp = pd.Timestamp(name_time or start).strftime("%Y%m%d_%H%M%S")
    path = root / folder / f"{event}_{label}_{cow}_{stamp}.csv"
    path.parent.mkdir(parents=True, exist_ok=True)
    pd.DataFrame({
        "Time": [f"{t:%Y-%m-%d %H:%M:%S}.{t.microsecond // 100000}" for t in times],
        "BNO055_AX": 999.0,  # never read
        "MPU9250_AX": acc[0], "MPU9250_AY": acc[1], "MPU9250_AZ": acc[2],
    }).to_csv(path, index=False)
    return path


def _morales(tmp_path, events):
    root = tmp_path / "morales_vargas"
    root.mkdir(parents=True)
    (root / "README.md").write_text("synthetic", encoding="utf-8")
    files = [_m_event(root, *e) for e in events]
    return root, _hash_file(tmp_path, root, files)


def test_morales_reads_mpu_in_g_and_time_from_the_time_column(tmp_path):
    # file name says 12:57:30, the data start at 13:00:00 (like file 418)
    root, hashes = _morales(tmp_path, [
        ("Resting", 418, "Resting", "1219", "2024-10-21 13:00:00", 20, (9.80665, 0.0, -9.80665), "2024-10-21 12:57:30"),
        ("Walking", 1, "Walking", "2016", "2024-05-15 23:59:59.5", 10),
    ])
    s = ext.load_morales_vargas(root, hashes).samples
    rest = s[s["animal_id"] == "1219"]
    assert rest["ax"].tolist() == [1.0] * 20 and rest["az"].tolist() == [-1.0] * 20 and (rest["ay"] == 0).all()
    assert rest["t_rel_ms"].tolist() == list(range(0, 2000, 100))
    walk = s[s["animal_id"] == "2016"]
    assert walk.groupby("day")["t_rel_ms"].min().to_dict() == {"2024-05-15": 0, "2024-05-16": 0}
    assert list(s.columns) == ext.OUTPUT_COLUMNS and s["t_rel_ms"].dtype == np.int64


def test_morales_label_table(tmp_path):
    misc = ext.MORALES_MISC
    labels = [("Walking", "Walking", "moving", ""), ("Grazing", "Grazing", "grazing", ""),
              ("Resting", "Resting", "resting", ""), (misc, "Standing", "resting", ""),
              (misc, "Trotting", "moving", ""), (misc, "Drinking", "drinking", ""),
              (misc, "Licking", "", "other_miscellaneous"), (misc, "Rising", "", "other_miscellaneous")]
    events = [(folder, i + 1, label, "1217", f"2024-05-14 1{i}:00:00", 5) for i, (folder, label, _, _) in enumerate(labels)]
    s = ext.load_morales_vargas(*_morales(tmp_path, events)).samples
    got = s.groupby("label_native")[["base_class", "exclusion_reason"]].first()
    for _, label, base, reason in labels:
        assert tuple(got.loc[label]) == (base, reason)


@pytest.mark.parametrize("folder,label,match", [
    ("Walking", "Standing", "expected in folder"),
    (ext.MORALES_MISC, "Sleeping", "not in the mapping table"),
])
def test_morales_wrong_folder_or_unknown_label_stops_the_load(tmp_path, folder, label, match):
    with pytest.raises(ValueError, match=match):
        ext.load_morales_vargas(*_morales(tmp_path, [(folder, 1, label, "1217", "2024-05-14 10:00:00", 5)]))


def test_morales_hash_mismatch_or_unrecorded_file_stops_the_load(tmp_path):
    root, hashes = _morales(tmp_path, [("Walking", 1, "Walking", "1217", "2024-05-14 10:00:00", 5)])
    text = hashes.read_text(encoding="utf-8")
    hashes.write_text("0" * 64 + text[64:], encoding="utf-8")
    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        ext.load_morales_vargas(root, hashes)
    _m_event(root, "Walking", 2, "Walking", "1217", "2024-05-14 11:00:00", 5)
    hashes.write_text(text, encoding="utf-8")
    with pytest.raises(ValueError, match="differ from the hash file"):
        ext.load_morales_vargas(root, hashes)


def test_morales_dedup_and_shared_label_conflict(tmp_path):
    loaded = ext.load_morales_vargas(*_morales(tmp_path, [
        ("Walking", 1, "Walking", "2016", "2024-05-15 10:00:00.0", 100),   # 10:00:00.0 - 10:00:09.9
        ("Walking", 2, "Walking", "2016", "2024-05-15 10:00:09.7", 100),   # 3 samples shared with event 1
        ("Grazing", 3, "Grazing", "2016", "2024-05-15 10:00:19.6", 50),    # 1 sample shared with event 2
    ]))
    s = loaded.samples
    assert len(s) == 100 + 97 + 49
    conflict = s[s["exclusion_reason"] == ext.MORALES_SHARED_CONFLICT]
    assert len(conflict) == 1 and conflict["label_native"].iloc[0] == "Grazing|Walking"
    assert conflict["base_class"].iloc[0] == ""
    items = {r["item"]: r["rows"] for r in loaded.accounting}
    assert items["rows_read"] == 250 and items["deduplicated"] == 4
    assert items["excluded:shared_label_conflict"] == 1
    assert items["mapped:moving"] == 196 and items["mapped:grazing"] == 49


def test_morales_shared_sample_with_different_values_is_an_error(tmp_path):
    with pytest.raises(ValueError, match="different acceleration"):
        ext.load_morales_vargas(*_morales(tmp_path, [
            ("Walking", 1, "Walking", "2016", "2024-05-15 10:00:00", 10),
            ("Walking", 2, "Walking", "2016", "2024-05-15 10:00:00.9", 10, (0.0, 0.0, 9.80665)),
        ]))


def test_morales_windows_before_and_after_merge(tmp_path):
    loaded = ext.load_morales_vargas(*_morales(tmp_path, [
        ("Walking", 1, "Walking", "2016", "2024-05-15 10:00:00", 100),
        ("Walking", 2, "Walking", "2016", "2024-05-15 10:00:10", 100),  # adjacent: 10 s + 10 s
    ]))
    merged = segments.make_windows(harmonise.harmonise(loaded.samples)[0])
    table = summarise_external.before_after_merge(loaded, merged).set_index("label")
    walk = table.loc["Walking"]
    assert (walk["events"], walk["windows_alone_ge142"], walk["windows_merged_ge142"]) == (2, 0, 1)
    assert table.loc["Grazing", "events"] == 0


# ── Summary command ───────────────────────────────────────────────────────────

def _summary_inputs(tmp_path):
    lines = [_v_row(1, _v_time(i), {I: "Ruminating", P: "Laying"}, x=0.1, y=-0.21, z=0.95) for i in range(300)]
    lines += [_v_row(2, _v_time(i), {L: "Walking"}) for i in range(150)]
    v_root, v_hashes = _versluijs(tmp_path, lines)
    m_root, m_hashes = _morales(tmp_path, [
        ("Resting", 1, "Resting", "1217", "2024-05-14 10:00:00", 160),
        (ext.MORALES_MISC, 2, "Drinking", "1217", "2024-05-14 11:00:00", 150),
    ])
    return ["--versluijs-dir", str(v_root), "--versluijs-hashes", str(v_hashes),
            "--morales-dir", str(m_root), "--morales-hashes", str(m_hashes)]


def test_summary_writes_only_aggregates_and_refuses_an_existing_folder(tmp_path):
    results = tmp_path / "results"
    args = ["--name", "syn_summary", "--results-dir", str(results), *_summary_inputs(tmp_path)]
    assert summarise_external.main(args) == 0
    folder = results / "syn_summary"
    assert {p.name for p in folder.iterdir()} == {
        "config.json", "run.log", "row_accounting.csv", "windows_per_class.csv",
        "windows_per_class_per_animal.csv", "morales_windows_before_after_merge.csv", "gravity_resting.csv"}

    counts = pd.read_csv(folder / "windows_per_class.csv", keep_default_na=False)
    by = counts.set_index(["dataset", "scheme", "class"])["windows_ge142"].to_dict()
    assert by[("versluijs", "3-class", "resting")] == 2 and by[("versluijs", "3-class", "moving")] == 1
    assert by[("morales_vargas", "2-class", "active")] == 1          # drinking counts as active
    assert ("morales_vargas", "3-class", "drinking") not in by       # and is excluded from 3 classes

    gravity = pd.read_csv(folder / "gravity_resting.csv", keep_default_na=False)
    rum = gravity[(gravity["label_native"] == "Intake=Ruminating|Posture=Laying") & (gravity["quantise"])]
    assert rum[["mean_ax", "mean_ay", "mean_az"]].iloc[0].tolist() == pytest.approx([0.096, -0.208, 0.944])

    for name in ["row_accounting.csv", "windows_per_class.csv", "windows_per_class_per_animal.csv",
                 "morales_windows_before_after_merge.csv", "gravity_resting.csv"]:
        columns = set(pd.read_csv(folder / name).columns)
        assert not columns & {"t_rel_ms", "t_ms", "ax", "ay", "az", "accel_x_mean"}

    config = json.loads((folder / "config.json").read_text(encoding="utf-8"))
    assert "step2/windows.py" in config["code_sha256"]
    assert config["harmonise"]["quantise"] is True and config["windows"]["min_samples"] == 142

    with pytest.raises(SystemExit, match="already exists"):
        summarise_external.main(args)
