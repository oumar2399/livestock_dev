"""Step 3: gravity alignment and feature sets A / B (synthetic data only)."""

import numpy as np
import pandas as pd
import pytest

from ml.step2 import windows
from ml.step3 import align, features


def _rotation_ok(r):
    assert np.allclose(r @ r.T, np.eye(3), atol=1e-9) and np.isclose(np.linalg.det(r), 1.0)


@pytest.mark.parametrize("g", [(0.3, -0.2, 0.9), (1.0, 0.0, 0.0), (0.0, -1.0, 0.1), (0.2, 0.1, -0.95),
                               (1e-3, 0.0, -1.0), (-0.5, 0.5, 0.0)])
def test_rotation_maps_the_mean_vector_to_plus_z_and_preserves_norms(g):
    r, case = align.rotation_to_z(g)
    assert case == "rodrigues"
    _rotation_ok(r)
    u = np.asarray(g) / np.linalg.norm(g)
    assert np.allclose(r @ u, [0, 0, 1], atol=1e-9)  # near -z, 1/(1+c) amplifies rounding
    x = np.random.default_rng(0).normal(0, 1, (100, 3))
    assert np.allclose(np.linalg.norm(x @ r.T, axis=1), np.linalg.norm(x, axis=1), atol=1e-9)


def test_parallel_case_is_the_identity():
    for g in [(0.0, 0.0, 1.0), (0.0, 0.0, 2.5), (1e-9, 0.0, 1.0)]:
        r, case = align.rotation_to_z(g)
        assert case == "identity" and np.array_equal(r, np.eye(3))


def test_antiparallel_case_is_180_degrees_about_x():
    for g in [(0.0, 0.0, -1.0), (0.0, 0.0, -0.98), (1e-6, 0.0, -1.0)]:
        r, case = align.rotation_to_z(g)
        assert case == "antiparallel_180_about_x" and np.array_equal(r, np.diag([1.0, -1.0, -1.0]))
        _rotation_ok(r)
        u = np.asarray(g) / np.linalg.norm(g)
        assert np.allclose(r @ u, [0, 0, 1], atol=1e-5)


def test_vector_without_direction_is_an_error():
    with pytest.raises(ValueError, match="no direction"):
        align.rotation_to_z((0.0, 0.0, 0.0))


def _samples(seed=0):
    """Two animal-days with different tilts; labelled, excluded and unlabelled samples."""
    rng = np.random.default_rng(seed)
    parts = []
    for animal, tilt in [("a1", (0.5, 0.0, 0.85)), ("a2", (0.0, -0.9, -0.3))]:
        n = 600
        acc = np.asarray(tilt) + rng.normal(0, 0.05, (n, 3))
        parts.append(pd.DataFrame({
            "dataset": "syn", "animal_id": animal, "day": "2026-01-01", "t_rel_ms": np.arange(n, dtype=np.int64) * 100,
            "ax": acc[:, 0], "ay": acc[:, 1], "az": acc[:, 2],
            "base_class": ["resting"] * 200 + [""] * 200 + ["moving"] * 200,
            "label_native": ["R"] * 200 + [""] * 200 + ["M"] * 200, "posture": "",
            "exclusion_reason": [""] * 200 + ["unlabeled"] * 200 + [""] * 200,
        }))
    return pd.concat(parts, ignore_index=True)


def test_alignment_uses_all_samples_and_maps_each_animal_day_mean_to_plus_z():
    s = _samples()
    before = s.copy()
    out, info = align.align_by_animal_day(s)
    pd.testing.assert_frame_equal(s, before)  # input untouched
    for animal, g in out.groupby("animal_id"):
        mean = g[["ax", "ay", "az"]].mean().to_numpy()
        assert np.allclose(mean / np.linalg.norm(mean), [0, 0, 1], atol=1e-12)
    norms = lambda t: np.linalg.norm(t[["ax", "ay", "az"]].to_numpy(), axis=1)
    assert np.allclose(norms(out), norms(s), atol=1e-12)
    assert np.allclose(features.msa(out), features.msa(s), atol=1e-12)  # MSA unchanged by alignment
    assert set(info["n_samples"]) == {600} and set(info["case"]) == {"rodrigues"}
    pd.testing.assert_frame_equal(out.drop(columns=["ax", "ay", "az"]), s.drop(columns=["ax", "ay", "az"]))


def test_alignment_ignores_labels():
    s = _samples()
    shuffled = s.assign(base_class=s["base_class"].sample(frac=1, random_state=1).to_numpy(),
                        label_native="X", posture="Laying", exclusion_reason="")
    a, _ = align.align_by_animal_day(s)
    b, _ = align.align_by_animal_day(shuffled)
    assert np.array_equal(a[["ax", "ay", "az"]].to_numpy(), b[["ax", "ay", "az"]].to_numpy())


def test_feature_b_on_a_known_window_and_same_windows_as_a():
    n = 150
    z = np.where(np.arange(n) % 2 == 0, 1.0, 1.5)  # |a| = 1.0 or 1.5 -> MSA = 0 or 0.5
    s = pd.DataFrame({"dataset": "syn", "animal_id": "a", "day": "d", "t_rel_ms": np.arange(n, dtype=np.int64) * 100,
                      "ax": 0.0, "ay": 0.0, "az": z, "base_class": "resting", "label_native": "R", "posture": ""})
    win = features.make_feature_windows(s)
    assert len(win) == 1
    assert win["msa_mean"].iloc[0] == pytest.approx(0.25) and win["msa_std"].iloc[0] == pytest.approx(0.25)  # ddof 0
    expected = windows.window_features({"x": s["ax"].to_numpy(), "y": s["ay"].to_numpy(), "z": z})
    for col, value in expected.items():
        assert win[col].iloc[0] == pytest.approx(value)
    assert features.FEATURE_SETS["B"] == features.FEATURE_SETS["A"] + ["msa_mean", "msa_std"]
    assert features.FEATURE_SETS["A"] == list(windows.FEATURE_COLUMNS)


def test_feature_b_uses_only_the_samples_present():
    n = 150
    keep = np.setdiff1d(np.arange(n), [10, 20, 30])  # 147 samples: a valid window
    z = 1.0 + 0.01 * np.arange(n)
    s = pd.DataFrame({"dataset": "syn", "animal_id": "a", "day": "d", "t_rel_ms": keep.astype(np.int64) * 100,
                      "ax": 0.0, "ay": 0.0, "az": z[keep], "base_class": "resting", "label_native": "R", "posture": ""})
    win = features.make_feature_windows(s)
    m = np.abs(z[keep] - 1.0)
    assert win["n_samples"].iloc[0] == 147
    assert win["msa_mean"].iloc[0] == pytest.approx(m.mean()) and win["msa_std"].iloc[0] == pytest.approx(m.std())
