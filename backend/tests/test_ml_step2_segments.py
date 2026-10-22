"""Step 2: shared segmenting and windowing rule (synthetic tables only)."""

import numpy as np
import pandas as pd
import pytest

from ml.step2 import segments, windows


def _samples(t_rel_ms, base="resting", label="Posture=Laying", posture="", animal="a1",
             day="2021-06-22", seed=0):
    t = np.asarray(t_rel_ms, dtype=np.int64)
    n = len(t)
    rng = np.random.default_rng(seed)

    def column(v):
        return np.array([v] * n if isinstance(v, str) else list(v), dtype=object)

    return pd.DataFrame({
        "dataset": "syn", "animal_id": animal, "day": day, "t_rel_ms": t,
        "ax": rng.normal(0, 0.1, n), "ay": rng.normal(0, 0.1, n), "az": rng.normal(1, 0.1, n),
        "base_class": column(base), "label_native": column(label), "posture": column(posture),
    })


def _slots(n_slots, missing=()):
    return np.array([s for s in range(n_slots) if s not in set(missing)]) * 100


def _n_segments(samples):
    seg = segments.assign_segments(samples)["segment_id"]
    return seg[seg >= 0].nunique()


def test_gap_of_exactly_1000_ms_does_not_split_but_1001_does():
    first = np.arange(150) * 100
    assert _n_segments(_samples(np.r_[first, first[-1] + 1000 + first])) == 1
    assert _n_segments(_samples(np.r_[first, first[-1] + 1001 + first])) == 2


def test_900_ms_dropout_keeps_the_segment_and_a_142_sample_window():
    samples = _samples(_slots(150, missing=range(50, 58)))  # 8 missing: one 900 ms step
    assert _n_segments(samples) == 1
    win = segments.make_windows(samples)
    assert win["n_samples"].tolist() == [142]


def test_142_samples_keep_a_window_141_drop_it():
    kept = segments.make_windows(_samples(_slots(150, missing=range(10, 90, 10))))     # 8 missing
    dropped = segments.make_windows(_samples(_slots(150, missing=range(10, 100, 10))))  # 9 missing
    assert kept["n_samples"].tolist() == [142] and dropped.empty
    full = segments.make_windows(_samples(_slots(300, missing=[5])))
    counts = segments.count_windows(full, ["dataset"])
    assert counts[["windows_ge142", "windows_eq150"]].iloc[0].tolist() == [2, 1]


def test_window_must_lie_inside_its_segment():
    assert len(segments.make_windows(_samples(_slots(149)))) == 0
    assert len(segments.make_windows(_samples(_slots(150)))) == 1
    assert len(segments.make_windows(_samples(_slots(299)))) == 1
    assert len(segments.make_windows(_samples(_slots(300)))) == 2
    # a window that would end in a missing tail is not created
    assert len(segments.make_windows(_samples(_slots(150, missing=[149])))) == 0


def test_unused_sample_and_class_change_end_a_segment():
    t = _slots(201)
    one_class = _samples(t)
    assert _n_segments(one_class) == 1 and len(segments.make_windows(one_class)) == 1

    unused = _samples(t, base=["resting"] * 100 + [""] + ["resting"] * 100)
    seg = segments.assign_segments(unused)["segment_id"].to_numpy()
    assert seg[100] == -1 and set(seg[:100]) == {0} and set(seg[101:]) == {1}
    assert segments.make_windows(unused).empty

    changed = _samples(t, base=["resting"] * 100 + ["grazing"] * 101)
    assert _n_segments(changed) == 2 and segments.make_windows(changed).empty


def test_animals_and_days_are_separate_segments():
    t = _slots(150)
    two = pd.concat([_samples(t, animal="a1"), _samples(t, animal="a2"),
                     _samples(t, animal="a1", day="2021-06-23")], ignore_index=True)
    assert _n_segments(two) == 3 and len(segments.make_windows(two)) == 3


def test_features_equal_window_features_on_present_samples():
    samples = _samples(_slots(150, missing=[3, 40, 77, 120]), seed=4)
    win = segments.make_windows(samples)
    expected = windows.window_features({"x": samples["ax"].to_numpy(), "y": samples["ay"].to_numpy(),
                                        "z": samples["az"].to_numpy()})
    assert win["n_samples"].iloc[0] == 146
    for col, value in expected.items():
        assert win[col].iloc[0] == pytest.approx(value, abs=1e-12)


def test_window_records_schemes_majority_label_and_posture():
    t = _slots(150)
    parts = [
        _samples(t, base="moving", label="Locomotion=Walking", animal="m"),
        _samples(t, base="grazing", label="Intake=Feeding/Grazing_Grazing head low", animal="g"),
        _samples(t, base="drinking", label="Intake=Drinking", animal="d"),
        _samples(t, base="resting", animal="r",
                 label=["Posture=Laying"] * 100 + ["Intake=Ruminating|Posture=Laying"] * 50,
                 posture=["Laying"] * 90 + [""] * 60),
    ]
    win = segments.make_windows(pd.concat(parts, ignore_index=True)).set_index("animal_id")
    assert win.loc[["m", "g", "d", "r"], "class_2"].tolist() == ["active", "active", "active", "resting"]
    assert win.loc[["m", "g", "d", "r"], "class_3"].tolist() == ["moving", "grazing", "", "resting"]
    r = win.loc["r"]
    assert (r["label_native"], r["label_native_share"]) == ("Posture=Laying", pytest.approx(100 / 150))
    assert (r["posture"], r["posture_share"]) == ("Laying", pytest.approx(90 / 150))
    assert win.loc["m", "posture"] == "" and win.loc["m", "t_rel_start_ms"] == 0


def test_duplicate_time_or_shared_slot_is_an_error():
    with pytest.raises(ValueError, match="Duplicate t_rel_ms"):
        segments.assign_segments(_samples(np.r_[0, 0, _slots(150)[1:]]))
    with pytest.raises(ValueError, match="same 100 ms slot"):
        segments.make_windows(_samples(np.r_[0, 40, _slots(150)[1:]]))


def test_input_must_be_relative_time_and_known_classes():
    samples = _samples(_slots(10))
    with pytest.raises(ValueError, match="absolute t_ms"):
        segments.validate_samples(samples.assign(t_ms=samples["t_rel_ms"]))
    with pytest.raises(ValueError, match="int64"):
        segments.validate_samples(samples.assign(t_rel_ms=samples["t_rel_ms"].astype(float)))
    with pytest.raises(ValueError, match="Unknown base classes"):
        segments.validate_samples(samples.assign(base_class="walking"))
    with pytest.raises(ValueError, match="missing columns"):
        segments.validate_samples(samples.drop(columns="posture"))


def test_window_table_has_no_absolute_time():
    win = segments.make_windows(_samples(_slots(150)))
    assert "t_ms" not in win.columns and "t_start_ms" not in win.columns
    assert list(win.columns) == segments.WINDOW_COLUMNS
