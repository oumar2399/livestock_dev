"""Step 3: pooled metrics, animal-level bootstrap, paired differences, decision rule."""

import numpy as np
import pandas as pd
import pytest

from ml.step3 import metrics

AB = ["a", "b"]


def _pred(rows, tier="T1", dataset="d"):
    """rows: [(seed, animal, y_true list, y_pred list)]."""
    parts = [pd.DataFrame({"tier": tier, "dataset": dataset, "seed": seed, "animal_id": animal,
                           "y_true": t, "y_pred": p}) for seed, animal, t, p in rows]
    return pd.concat(parts, ignore_index=True)


def test_pooled_balanced_accuracy_is_not_the_mean_of_folds():
    a1 = (["a", "a", "b", "b"], ["a", "a", "a", "b"])   # fold BA (1 + 0.5) / 2 = 0.75
    a2 = (["a", "a", "a", "a"], ["a", "a", "b", "b"])   # only class a present: fold BA 0.5
    pred = _pred([(42, "a1", *a1), (42, "a2", *a2)])
    pooled = metrics.pooled_by_seed(pred, AB)[("T1", "d")][42]
    # pooled: class a 4/6 correct, class b 1/2 correct -> (2/3 + 1/2) / 2 = 7/12
    assert pooled["balanced_accuracy"] == pytest.approx(7 / 12)
    assert np.mean([0.75, 0.5]) == pytest.approx(0.625)
    assert pooled["confusion_matrix"] == [[4, 2], [1, 1]]
    cm = metrics.confusion(pred["y_true"], pred["y_pred"], AB)
    assert metrics.balanced_accuracy(cm) == pytest.approx(7 / 12)


def _cms(per_animal_true_pred, n_seeds=2, flip_seed=1):
    """[seed, animal, k, k]; on seed `flip_seed` the first prediction of each animal is flipped."""
    out = []
    for s in range(n_seeds):
        row = []
        for t, p in per_animal_true_pred:
            p = list(p)
            if s == flip_seed:
                p[0] = "b" if p[0] == "a" else "a"
            row.append(metrics.confusion(t, p, AB))
        out.append(row)
    return np.array(out)


ALL_CLASSES = [(["a", "a", "b", "b"], ["a", "b", "b", "b"]), (["a", "b", "b"], ["a", "a", "b"]),
               (["a", "a", "b"], ["a", "a", "a"]), (["a", "b"], ["b", "b"])]


def test_resamples_are_deterministic_and_draw_animals_with_replacement():
    c1, c2 = metrics.resample_counts(4, 200, 0), metrics.resample_counts(4, 200, 0)
    assert np.array_equal(c1, c2) and c1.shape == (200, 4)
    assert (c1.sum(axis=1) == 4).all() and (c1 >= 0).all()
    assert not np.array_equal(c1, metrics.resample_counts(4, 200, 1))


def test_bootstrap_averages_per_seed_pooled_balanced_accuracy():
    cms = _cms(ALL_CLASSES)
    counts = np.array([[1, 1, 1, 1], [2, 0, 1, 1]])
    ba = metrics.bootstrap_ba(cms, counts)
    for r, row in enumerate(counts):
        per_seed = [metrics.balanced_accuracy(np.tensordot(row, cms[s], axes=1)) for s in range(cms.shape[0])]
        assert ba[r] == pytest.approx(np.mean(per_seed))


def test_paired_bootstrap_uses_the_same_resamples_for_both_configurations():
    ref = _cms(ALL_CLASSES)
    new = _cms([(t, t) for t, _ in ALL_CLASSES])  # perfect predictions, same true labels
    counts = metrics.resample_counts(4, 300, 0)
    diff = metrics.paired_difference(new, ref, counts)
    assert np.allclose(diff, metrics.bootstrap_ba(new, counts) - metrics.bootstrap_ba(ref, counts), equal_nan=True)
    # an unpaired bootstrap (other resamples for one configuration) gives other differences
    other = metrics.bootstrap_ba(new, metrics.resample_counts(4, 300, 1)) - metrics.bootstrap_ba(ref, counts)
    assert not np.allclose(diff, other, equal_nan=True)


def test_resamples_without_a_class_are_discarded_and_flagged():
    only_first_has_b = [(["a", "b"], ["a", "b"]), (["a", "a"], ["a", "a"]), (["a"], ["a"]), (["a", "a"], ["a", "b"])]
    cms = _cms(only_first_has_b)
    counts = metrics.resample_counts(4, 1000, 0)
    ba = metrics.bootstrap_ba(cms, counts)
    assert np.array_equal(np.isnan(ba), counts[:, 0] == 0)
    result = metrics.interval(ba)
    assert result["n_discarded"] == int((counts[:, 0] == 0).sum()) > 50 and result["unreliable"] is True
    ok = metrics.interval(metrics.bootstrap_ba(_cms(ALL_CLASSES), counts))
    assert ok["n_discarded"] == 0 and ok["unreliable"] is False and ok["ci_low"] <= ok["ci_high"]


def test_unreliable_threshold_is_more_than_five_percent():
    values = np.zeros(1000)
    values[:50] = np.nan
    assert metrics.interval(values)["unreliable"] is False
    values[50] = np.nan
    assert metrics.interval(values)["unreliable"] is True


def test_paired_configurations_with_different_windows_are_refused():
    ref = _cms([(["a", "b"], ["a", "b"]), (["a", "a"], ["a", "a"])])
    new = _cms([(["a", "b"], ["a", "b"]), (["a", "b"], ["a", "b"])])
    with pytest.raises(ValueError, match="discard different resamples"):
        metrics.paired_difference(new, ref, metrics.resample_counts(2, 200, 0))


def _d(point, low, high):
    return {"point": point, "ci_low": low, "ci_high": high}


@pytest.mark.parametrize("directions,verdict,n_pos,n_excl", [
    ([_d(0.02, 0.01, 0.03), _d(0.01, 0.002, 0.02), _d(0.01, -0.01, 0.03)], metrics.IMPROVEMENT, 3, 2),
    ([_d(0.02, 0.01, 0.03), _d(0.01, 0.002, 0.02), _d(0.01, 0.001, 0.03)], metrics.IMPROVEMENT, 3, 3),
    ([_d(0.02, 0.01, 0.03), _d(0.01, -0.002, 0.02), _d(0.01, -0.01, 0.03)], metrics.NO_EFFECT, 3, 1),
    ([_d(0.02, 0.01, 0.03), _d(0.01, 0.002, 0.02), _d(-0.01, -0.03, -0.001)], metrics.NO_EFFECT, 2, 3),
    ([_d(0.0, -0.01, 0.01), _d(0.05, 0.01, 0.09), _d(0.05, 0.01, 0.09)], metrics.NO_EFFECT, 2, 2),
    ([_d(0.02, np.nan, np.nan), _d(0.01, 0.002, 0.02), _d(0.01, -0.01, 0.03)], metrics.NO_EFFECT, 3, 1),
])
def test_decision_rule(directions, verdict, n_pos, n_excl):
    out = metrics.decision(directions)
    assert (out["verdict"], out["n_positive"], out["n_interval_excludes_0"]) == (verdict, n_pos, n_excl)


def test_decision_rule_needs_three_directions():
    with pytest.raises(ValueError, match="three T2 directions"):
        metrics.decision([_d(0.1, 0.05, 0.2)] * 2)


def test_per_animal_ba_only_for_animals_with_five_windows_of_every_class():
    lab = pd.DataFrame({"dataset": "d", "animal_id": ["x"] * 10 + ["y"] * 9,
                        "label": ["a"] * 5 + ["b"] * 5 + ["a"] * 5 + ["b"] * 4})
    eligible = metrics.eligible_animals(lab, AB)
    assert eligible == {"d": ["x"]}
    pred = _pred([(42, "x", ["a"] * 5 + ["b"] * 5, ["a"] * 5 + ["a"] * 5),
                  (42, "y", ["a"] * 5 + ["b"] * 4, ["a"] * 9)])
    table = metrics.per_animal_ba(pred, eligible, AB)
    assert table["animal_id"].tolist() == ["x"] and table["balanced_accuracy_mean"].iloc[0] == pytest.approx(0.5)
