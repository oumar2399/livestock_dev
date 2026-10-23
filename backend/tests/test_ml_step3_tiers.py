"""Step 3: T1 (leave one animal out) and T2 (leave one dataset out) never train on held-out data."""

import numpy as np
import pandas as pd
import pytest

from ml.step3 import tiers

CLASSES = ["active", "resting"]


def _labelled(datasets=("d1", "d2", "d3"), animals=3, per_class=4):
    rows = []
    for d in datasets:
        for a in range(animals):
            for cls in CLASSES:
                rows += [{"dataset": d, "animal_id": f"{d}_a{a}", "label": cls}] * per_class
    lab = pd.DataFrame(rows)
    lab["row_id"] = np.arange(len(lab), dtype=float)
    return lab


class SpyForest:
    """Records the training rows (by the row_id feature) of every fit."""

    def __init__(self):
        self.fits = []

    def build(self, seed):
        spy = self

        class Model:
            def fit(self, X, y):
                spy.fits.append((seed, X[:, 0].astype(int)))
                self.first = y[0]
                return self

            def predict(self, X):
                return np.array([self.first] * len(X), dtype=object)

        return Model()


def test_t1_never_trains_on_the_held_out_animal_nor_outside_its_dataset():
    lab = _labelled()
    folds = tiers.t1_folds(lab)
    assert len(folds) == 9
    for f in folds:
        tiers.check_fold(lab, f, CLASSES)
        assert f.held_out not in set(lab.loc[f.train, "animal_id"])
        assert set(lab.loc[f.train, "dataset"]) == {f.dataset}
        assert set(lab.loc[f.test, "animal_id"]) == {f.held_out}


def test_t2_never_trains_on_the_held_out_dataset():
    lab = _labelled()
    folds = tiers.t2_folds(lab)
    assert [f.held_out for f in folds] == ["d1", "d2", "d3"]
    for f in folds:
        tiers.check_fold(lab, f, CLASSES)
        assert f.dataset not in set(lab.loc[f.train, "dataset"])
        assert f.train.sum() + f.test.sum() == len(lab)  # all windows of the two others, no subsampling


def test_predict_trains_each_fold_only_on_its_training_rows():
    lab = _labelled()
    folds = tiers.t1_folds(lab) + tiers.t2_folds(lab)
    spy = SpyForest()
    pred = tiers.predict(lab, ["row_id"], CLASSES, folds, (42, 43), spy)
    assert len(spy.fits) == 2 * len(folds)
    for (seed, rows), fold in zip(spy.fits, folds * 2):
        assert set(rows) == set(np.flatnonzero(fold.train))
        held = lab.iloc[rows]
        if fold.tier == "T1":
            assert fold.held_out not in set(held["animal_id"])
        else:
            assert fold.dataset not in set(held["dataset"])
    # one prediction per held-out window, tier and seed
    assert pred.groupby(["tier", "seed"]).size().to_dict() == {("T1", 42): len(lab), ("T1", 43): len(lab),
                                                               ("T2", 42): len(lab), ("T2", 43): len(lab)}


def test_training_fold_without_a_class_stops_before_any_training():
    lab = _labelled(datasets=("d1",), animals=2)
    lab = lab[~((lab["animal_id"] == "d1_a1") & (lab["label"] == "active"))].reset_index(drop=True)
    spy = SpyForest()
    with pytest.raises(ValueError, match="absent from training"):
        tiers.predict(lab, ["row_id"], CLASSES, tiers.t1_folds(lab), (42,), spy)
    assert spy.fits == []
