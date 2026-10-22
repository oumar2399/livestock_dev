"""Step 2: harmonisation to the Versluijs collar's range and 0.016 g grid."""

import numpy as np
import pandas as pd
import pytest

from ml.step2 import datasets, harmonise


def _table(values):
    v = np.asarray(values, dtype=float)
    return pd.DataFrame({"animal_id": "a", "ax": v, "ay": -v, "az": v / 2})


def test_clip_limits():
    out, settings = harmonise.harmonise(_table([-3.0, -2.048, 0.0, 2.032, 2.045, 5.0]))
    assert out["ax"].tolist() == [-2.048, -2.048, 0.0, 2.032, 2.032, 2.032]
    # ay = -ax: -2.045 is inside the range and rounds to the lowest step
    assert out["ay"].tolist() == [2.032, 2.032, 0.0, -2.032, -2.048, -2.048]
    assert settings["clip_g"] == [-2.048, 2.032] and settings["quantise"] is True


def test_values_land_on_the_grid():
    x = np.random.default_rng(0).uniform(-3, 3, 5000)
    out, _ = harmonise.harmonise(_table(x))
    for col in ["ax", "ay", "az"]:
        k = out[col].to_numpy() / 0.016
        assert np.allclose(k, np.round(k), atol=1e-9)
        assert k.min() >= -128 - 1e-9 and k.max() <= 127 + 1e-9
    clipped = np.clip(x, -2.048, 2.032)
    assert np.abs(out["ax"].to_numpy() - clipped).max() <= 0.008 + 1e-9


def test_quantise_false_only_clips():
    x = np.random.default_rng(1).uniform(-3, 3, 1000)
    out, settings = harmonise.harmonise(_table(x), quantise=False)
    assert np.array_equal(out["ax"].to_numpy(), np.clip(x, -2.048, 2.032))
    assert settings["quantise"] is False and settings["step_g"] is None


def test_idempotent():
    x = np.random.default_rng(2).uniform(-3, 3, 1000)
    for quantise in (True, False):
        once, _ = harmonise.harmonise(_table(x), quantise=quantise)
        twice, _ = harmonise.harmonise(once, quantise=quantise)
        pd.testing.assert_frame_equal(once, twice)


def test_values_already_on_the_versluijs_grid_are_unchanged():
    grid = [float(f"{k * 0.016:.3f}") for k in range(-128, 128)]  # as read from the file
    out, _ = harmonise.harmonise(_table(grid))
    assert out["ax"].tolist() == grid


def test_works_on_a_canonical_table_and_copies():
    raw, _ = datasets.make_synthetic("syn", 0, n_animals=1, n_days=1, bouts_per_day=2)
    before = raw.copy()
    out, _ = harmonise.harmonise(raw)
    pd.testing.assert_frame_equal(raw, before)  # input untouched
    assert list(out.columns) == list(raw.columns)
    pd.testing.assert_frame_equal(out.drop(columns=["ax", "ay", "az"]), raw.drop(columns=["ax", "ay", "az"]))


def test_rejects_missing_columns_and_nan():
    with pytest.raises(ValueError, match="Missing acceleration"):
        harmonise.harmonise(_table([0.0]).drop(columns="az"))
    with pytest.raises(ValueError, match="NaN"):
        harmonise.harmonise(_table([0.0, np.nan]))
