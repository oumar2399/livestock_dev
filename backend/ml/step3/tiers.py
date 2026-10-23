"""Evaluation tiers (protocol §6, Amendment 1 item 4).

T1: within each dataset, leave one animal out (animals with no window in the
    scheme do not appear in the table, so they are skipped).
T2: leave one dataset out: train on all windows of the two other datasets,
    no weighting.
A fold whose training set lacks a class of the scheme stops the run; every
fold is checked before any model is trained.
"""

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Fold:
    tier: str
    dataset: str      # dataset of the held-out windows
    held_out: str     # T1: animal_id; T2: dataset
    train: np.ndarray  # boolean masks over the labelled window table
    test: np.ndarray


def t1_folds(labelled: pd.DataFrame) -> list:
    ds, animal = labelled["dataset"].to_numpy(), labelled["animal_id"].to_numpy()
    folds = []
    for dataset in sorted(set(ds)):
        for a in sorted(set(animal[ds == dataset])):
            test = (ds == dataset) & (animal == a)
            folds.append(Fold("T1", dataset, a, (ds == dataset) & ~test, test))
    return folds


def t2_folds(labelled: pd.DataFrame) -> list:
    ds = labelled["dataset"].to_numpy()
    return [Fold("T2", d, d, ds != d, ds == d) for d in sorted(set(ds))]


def check_fold(labelled: pd.DataFrame, fold: Fold, classes) -> None:
    """Held-out data never in training; every class present in training."""
    if (fold.train & fold.test).any() or not fold.test.any():
        raise ValueError(f"{fold.tier} {fold.held_out}: invalid fold masks")
    ds, animal = labelled["dataset"].to_numpy(), labelled["animal_id"].to_numpy()
    if fold.tier == "T1":
        if set(zip(ds[fold.train], animal[fold.train])) & set(zip(ds[fold.test], animal[fold.test])):
            raise ValueError(f"T1 {fold.dataset}/{fold.held_out}: held-out animal in training")
        if set(ds[fold.train]) != {fold.dataset}:
            raise ValueError(f"T1 {fold.dataset}/{fold.held_out}: training outside the dataset")
    else:
        if fold.dataset in set(ds[fold.train]):
            raise ValueError(f"T2 {fold.dataset}: held-out dataset in training")
    missing = set(classes) - set(labelled["label"].to_numpy()[fold.train])
    if missing:
        raise ValueError(f"{fold.tier} {fold.dataset}/{fold.held_out}: class(es) {sorted(missing)} absent "
                         "from training; the run stops (Amendment 1, item 4)")


def predict(labelled: pd.DataFrame, feature_columns, classes, folds, seeds, forest) -> pd.DataFrame:
    """One prediction per held-out window, fold and seed. `row` indexes `labelled`."""
    for fold in folds:
        check_fold(labelled, fold, classes)
    X = labelled[list(feature_columns)].to_numpy(dtype=np.float64)
    y = labelled["label"].to_numpy(dtype=object)
    animal = labelled["animal_id"].to_numpy(dtype=object)
    parts = []
    for seed in seeds:
        for fold in folds:
            model = forest.build(seed).fit(X[fold.train], y[fold.train])
            rows = np.flatnonzero(fold.test)
            parts.append(pd.DataFrame({
                "tier": fold.tier, "dataset": fold.dataset, "held_out": fold.held_out, "seed": int(seed),
                "row": rows, "animal_id": animal[rows], "y_true": y[rows],
                "y_pred": np.asarray(model.predict(X[fold.test]), dtype=object),
            }))
    return pd.concat(parts, ignore_index=True)
