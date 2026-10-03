"""
PC test (pytest): the firmware Welford accumulator matches batch statistics.

Tested code: class Moments in m5stack/b4_protocol.py, the module deployed on the
M5Stack, loaded as-is. Reference: numpy mean / std(ddof=0) / min / max, the same
statistics as extract_window_features() in ml/train_v2.py.

Float64 here, so the tolerance is tight. The float32 behaviour of the ESP32 is
measured on the device by m5stack/tests/bench_welford_device.py (separate script,
not collected by pytest).

Usage:
    pytest tests/test_welford_consistency.py      # through the normal test runner
    python tests/test_welford_consistency.py      # readable report, no database
"""
import random
from pathlib import Path

import numpy as np
import pytest

from firmware_helpers import load_firmware

TOLERANCE = 1e-9
WINDOW_SAMPLES = 150
REAL_WINDOWS = 20
DATASET = Path(__file__).resolve().parents[1] / "ml" / "data" / "cow1.csv"
AXES = ("AccX", "AccY", "AccZ")

Moments = load_firmware("b4_protocol").Moments


def firmware_stats(values):
    moments = Moments()
    for value in values:
        moments.add(value)
    mean, std, minimum, maximum = moments.values()
    return {"mean": mean, "std": std, "min": minimum, "max": maximum}


def batch_stats(values):
    array = np.asarray(values, dtype=np.float64)
    return {"mean": array.mean(), "std": array.std(ddof=0), "min": array.min(), "max": array.max()}


def compare(values):
    firmware, batch = firmware_stats(values), batch_stats(values)
    return [(key, batch[key], firmware[key], abs(batch[key] - firmware[key])) for key in batch]


def synthetic_cases():
    rng = random.Random(42)
    return {
        "resting": [1.0 + rng.gauss(0, 0.01) for _ in range(WINDOW_SAMPLES)],
        "active": [rng.uniform(-2.0, 2.0) for _ in range(WINDOW_SAMPLES)],
        "constant": [0.5] * WINDOW_SAMPLES,
        "ramp": [i * 0.001 for i in range(WINDOW_SAMPLES)],
        "n_equals_1": [0.734],
        "n_equals_2": [0.1, 0.9],
        "large_offset": [1000.0 + rng.gauss(0, 0.001) for _ in range(WINDOW_SAMPLES)],
    }


def real_windows():
    """Consecutive 150-sample windows per axis from the Japanese Black dataset (g units)."""
    import pandas as pd

    frame = pd.read_csv(DATASET, usecols=list(AXES), nrows=WINDOW_SAMPLES * REAL_WINDOWS)
    for axis in AXES:
        column = frame[axis].dropna().to_numpy(dtype=np.float64)
        for index in range(len(column) // WINDOW_SAMPLES):
            yield f"{DATASET.name}/{axis}/window{index}", column[index * WINDOW_SAMPLES:(index + 1) * WINDOW_SAMPLES]


@pytest.mark.parametrize("label", sorted(synthetic_cases()))
def test_firmware_moments_match_batch_on_synthetic_cases(label):
    for key, batch, firmware, diff in compare(synthetic_cases()[label]):
        assert diff <= TOLERANCE, f"{label}/{key}: batch={batch} firmware={firmware} diff={diff}"


def test_firmware_moments_match_batch_on_real_data():
    if not DATASET.is_file():
        pytest.skip(f"Dataset missing: expected Japanese Black cow1.csv at {DATASET}")
    windows = list(real_windows())
    assert len(windows) == len(AXES) * REAL_WINDOWS
    for label, values in windows:
        for key, batch, firmware, diff in compare(values):
            assert diff <= TOLERANCE, f"{label}/{key}: batch={batch} firmware={firmware} diff={diff}"


if __name__ == "__main__":
    cases = list(synthetic_cases().items())
    if DATASET.is_file():
        cases += list(real_windows())
    else:
        print(f"Dataset missing, real-data windows skipped: expected {DATASET}")
    worst = 0.0
    for label, values in cases:
        for key, batch, firmware, diff in compare(values):
            worst = max(worst, diff)
            if diff > TOLERANCE:
                print(f"FAIL {label}/{key}: batch={batch!r} firmware={firmware!r} diff={diff:.3e}")
    print(f"{len(cases)} windows checked, max |firmware - batch| = {worst:.3e} (tolerance {TOLERANCE:.0e})")
    print("PASS" if worst <= TOLERANCE else "FAIL")
