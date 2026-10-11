"""Step 2, Step B: device-matched preprocessing (low-pass, then 10 Hz point sampling)."""

import numpy as np
import pandas as pd
import pytest
from scipy import signal

from ml.step2 import labels, preprocess


@pytest.mark.parametrize("order", [1, 2])
def test_lowpass_is_minus_3_db_at_the_cutoff(order):
    sos = preprocess.lowpass_sos(5.1, 25, order)
    _, h = signal.sosfreqz(sos, worN=[5.1, 1.0, 10.0], fs=25)
    gain = np.abs(h)
    assert gain[0] == pytest.approx(1 / np.sqrt(2), abs=1e-6)
    assert gain[1] > 0.95          # slow posture / walking content kept
    assert gain[2] < gain[0]       # faster content attenuated


def test_lowpass_starts_in_steady_state():
    sos = preprocess.lowpass_sos(5.1, 25, 1)
    y = preprocess.lowpass(np.full(50, -0.98), sos)
    assert np.allclose(y, -0.98)   # no artificial step at the segment start


def _raw(t_ms, labels_=None, value=None):
    n = len(t_ms)
    return pd.DataFrame({
        "dataset": "japanese_black", "animal_id": "cow1", "day": "2020-06-12",
        "t_ms": np.asarray(t_ms, dtype="int64"),
        "ax": np.zeros(n) if value is None else value, "ay": np.zeros(n), "az": -np.ones(n),
        "label_native": labels_ if labels_ is not None else ["RES"] * n,
    })


def _run(raw):
    return preprocess.device_lp_point_10hz(raw, "Asia/Tokyo", native_hz=25)


def test_point_sampling_takes_one_reading_per_100_ms_with_its_label():
    t = np.arange(0, 4000, 40)                     # 25 Hz, 4 s
    lab = ["RES"] * 50 + ["MOV"] * 50
    out = _run(_raw(t, lab, value=np.arange(len(t), dtype=float)))
    assert (np.diff(out["t_ms"]) == 100).all()
    assert out["segment_id"].nunique() == 1
    # tick 2000 ms hits raw sample 50 exactly -> its label, not an average
    assert out.loc[out["t_ms"] == 2000, "label_native"].item() == "MOV"
    assert out.loc[out["t_ms"] == 1900, "label_native"].item() == "RES"


def test_gap_over_300_ms_starts_a_new_segment():
    t = np.r_[np.arange(0, 2000, 40), np.arange(2400, 4400, 40)]   # 400 ms gap
    out = _run(_raw(t))
    assert out["segment_id"].nunique() == 2
    assert out["t_ms"].min() == 0 and 2400 in set(out["t_ms"])


def test_tick_without_a_sample_within_20_ms_ends_the_block():
    t = np.arange(0, 4000, 40)
    t = t[(t < 960) | (t > 1040)]          # hole 920 -> 1080 ms: tick 1000 is 80 ms from any sample
    out = _run(_raw(t))
    assert 1000 not in set(out["t_ms"])
    assert out["segment_id"].nunique() == 2
    assert (out.groupby("segment_id")["t_ms"].diff().dropna() == 100).all()


def test_each_block_is_filtered_from_its_own_first_sample():
    t = np.r_[np.arange(0, 2000, 40), np.arange(2400, 4400, 40)]
    value = np.r_[np.zeros(50), np.ones(50)]           # level jumps across the gap
    out = _run(_raw(t, value=value))
    second = out[out["t_ms"] >= 2400]
    assert np.allclose(second["ax"], 1.0)              # no carry-over from the first block


def test_both_label_maps_cover_the_same_native_labels():
    old = labels.load_label_map("active_resting_v1")
    new = labels.load_label_map("active_inactive_v1")
    assert set(old.maps["japanese_black"]) == set(new.maps["japanese_black"])
    assert old.excluded == new.excluded
    assert new.classes == ("Active", "Inactive")
